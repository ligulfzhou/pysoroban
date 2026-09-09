import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


class DifferentialTests(unittest.TestCase):
    @unittest.skipUnless(NODE, "Node.js is required for Wasm execution")
    def test_typed_ir_matches_generated_wasm(self):
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "differential_test.py"),
                "--node",
                NODE,
                "--json",
            ],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result, {"failed": [], "matched": 55, "total": 55})


if __name__ == "__main__":
    unittest.main()
