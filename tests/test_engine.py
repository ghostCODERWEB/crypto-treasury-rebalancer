import json
import unittest
from cryptolab import *

EXAMPLE = json.loads(
    '{"cash": "1000", "cash_floor": "100", "fee_bps": 30, "assets": [{"symbol": "ETH", "price": "2000", "units": "1", "target_weight": "0.5"}, {"symbol": "BTC", "price": "50000", "units": "0", "target_weight": "0.4"}]}'
)


class EngineTests(unittest.TestCase):
    def test_reserve(self):
        r = analyze(EXAMPLE)
        self.assertGreaterEqual(Decimal(r["cash"]), Decimal("100"))

    def test_conservation(self):
        r = analyze(EXAMPLE)
        self.assertEqual(
            Decimal(r["initial_value"]) - Decimal(r["final_value"]), Decimal(r["fees"])
        )

    def test_weights(self):
        d = {
            **EXAMPLE,
            "assets": [{**a, "target_weight": "0.8"} for a in EXAMPLE["assets"]],
        }
        with self.assertRaises(ValueError):
            analyze(d)

    def test_deterministic(self):
        self.assertEqual(analyze(EXAMPLE), analyze(EXAMPLE))

    def test_cli_json(self):
        import subprocess, sys

        result = subprocess.run(
            [sys.executable, "-m", "cryptolab", "examples/input.json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), analyze(EXAMPLE))

    def test_cli_csv(self):
        import subprocess, sys, csv, io

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cryptolab",
                "examples/input.json",
                "--format",
                "csv",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            list(csv.reader(io.StringIO(result.stdout)))[0], ["path", "value"]
        )

    def test_duplicate_json_keys(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                load_input(path)

    def test_atomic_output(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            self.assertEqual(main(["examples/input.json", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text()), analyze(EXAMPLE))

    def test_input_unchanged(self):
        import copy

        before = copy.deepcopy(EXAMPLE)
        analyze(EXAMPLE)
        self.assertEqual(before, EXAMPLE)


if __name__ == "__main__":
    unittest.main()
