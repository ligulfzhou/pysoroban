import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from pysoroban.cli import main


VALID_SOURCE = """
from pysoroban import contract, i32, public

@contract
class Checked:
    @public
    def double(self, value: i32) -> i32:
        return value * 2
"""

EVENT_SOURCE = """
from pysoroban import Address, Topic, contract, event, events, public, u64

@event
class Updated:
    owner: Topic[Address]
    value: u64

@contract
class Meter:
    @public
    def publish(self, owner: Address, value: u64) -> None:
        events.publish(Updated(owner, value))
"""


class CliTests(unittest.TestCase):
    def test_check_reports_contract_without_writing_wasm(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "checked.py"
            source.write_text(VALID_SOURCE, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["check", str(source), "--json"])

            result = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["contract"], "Checked")
            self.assertEqual(result["functions"], ["double"])
            self.assertEqual(result["status"], "ok")
            self.assertFalse((Path(directory) / "dist").exists())

    def test_check_returns_nonzero_for_invalid_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.py"
            source.write_text("x = 1\n", encoding="utf-8")
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                exit_code = main(["check", str(source)])

            self.assertEqual(exit_code, 1)
            self.assertIn("exactly one @contract class", stderr.getvalue())

    def test_inspect_emits_machine_readable_function_and_event_abi(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "meter.py"
            source.write_text(EVENT_SOURCE, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["inspect", str(source), "--json"])

            abi = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(abi["contract"], "Meter")
            self.assertEqual(abi["functions"][0]["inputs"][0], {"name": "owner", "type": "Address"})
            self.assertEqual(abi["events"][0]["prefix_topics"], ["updated"])
            self.assertEqual(abi["events"][0]["topics"], [{"name": "owner", "type": "Address"}])
            self.assertEqual(abi["events"][0]["data"], [{"name": "value", "type": "u64"}])

    def test_verify_compares_rebuilt_wasm_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "checked.py"
            wasm = Path(directory) / "checked.wasm"
            source.write_text(VALID_SOURCE, encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["build", str(source), "--output", str(wasm)]), 0)

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["verify", str(source), "--wasm", str(wasm), "--json"])
            result = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["expected_sha256"], result["actual_sha256"])

            wasm.write_bytes(wasm.read_bytes() + b"changed")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["verify", str(source), "--wasm", str(wasm), "--json"]), 1)


if __name__ == "__main__":
    unittest.main()
