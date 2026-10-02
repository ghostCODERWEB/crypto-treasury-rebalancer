"""Plan deterministic treasury rebalances with transaction fees, reserve floors and trade thresholds."""

import json

from decimal import Decimal, localcontext


def number(value):
    n = Decimal(str(value))
    if not n.is_finite() or n < 0:
        raise ValueError("finite nonnegative value required")
    return n


def analyze(data):
    with localcontext() as ctx:
        ctx.prec = 50
        cash = number(data["cash"])
        floor = number(data.get("cash_floor", 0))
        fee = number(data.get("fee_bps", 30)) / 10000
        minimum = number(data.get("min_trade_value", 0))
        if cash < floor or fee >= 1:
            raise ValueError("invalid reserve or fee")
        assets = data["assets"]
        names = set()
        portfolio = cash
        weight = Decimal(0)
        rows = []
        for asset in assets:
            symbol = asset["symbol"]
            if symbol in names:
                raise ValueError("duplicate asset")
            names.add(symbol)
            price = number(asset["price"])
            units = number(asset["units"])
            target = number(asset["target_weight"])
            if price == 0 or target > 1:
                raise ValueError("invalid price or weight")
            value = price * units
            portfolio += value
            weight += target
            rows.append(
                {
                    "symbol": symbol,
                    "price": price,
                    "units": units,
                    "value": value,
                    "weight": target,
                }
            )
        if weight > 1:
            raise ValueError("weights exceed one")
        trades = []
        fees = Decimal(0)
        for row in rows:
            desired = portfolio * row["weight"]
            excess = row["value"] - desired
            if excess > 0 and excess >= minimum:
                units = excess / row["price"]
                cost = excess * fee
                row["units"] -= units
                cash += excess - cost
                fees += cost
                trades.append(
                    {
                        "symbol": row["symbol"],
                        "side": "sell",
                        "units": str(units),
                        "value": str(excess),
                        "fee": str(cost),
                    }
                )
        for row in rows:
            current = row["units"] * row["price"]
            deficit = max(portfolio * row["weight"] - current, Decimal(0))
            available = max(cash - floor, Decimal(0)) / (1 + fee)
            value = min(deficit, available)
            if value > 0 and value >= minimum:
                units = value / row["price"]
                cost = value * fee
                row["units"] += units
                cash -= value + cost
                fees += cost
                trades.append(
                    {
                        "symbol": row["symbol"],
                        "side": "buy",
                        "units": str(units),
                        "value": str(value),
                        "fee": str(cost),
                    }
                )
        final = cash + sum(row["units"] * row["price"] for row in rows)
        return {
            "initial_value": str(portfolio),
            "final_value": str(final),
            "cash": str(cash),
            "fees": str(fees),
            "trades": trades,
            "positions": [
                {
                    "symbol": r["symbol"],
                    "units": str(r["units"]),
                    "value": str(r["units"] * r["price"]),
                    "target_value": str(portfolio * r["weight"]),
                }
                for r in rows
            ],
            "execution_order": "sells first, then buys in input order",
        }


import argparse
import csv
import io
import sys
from pathlib import Path


def load_input(path):
    raw = Path(path).read_text(encoding="utf-8")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("invalid JSON constant: " + value)

    data = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def flatten(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(flatten(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix, json.dumps(value, ensure_ascii=False)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input file")
    parser.add_argument("--output", help="write result atomically to a file")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args(argv)
    try:
        result = analyze(load_input(args.input))
        if args.format == "json":
            content = (
                json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
            )
        else:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["path", "value"])
            writer.writerows(flatten(result))
            content = buffer.getvalue()
        if args.output:
            import os, tempfile

            target = Path(args.output)
            fd, temporary = tempfile.mkstemp(
                prefix="." + target.name + ".", dir=target.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(content)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            sys.stdout.write(content)
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
