import unittest

from pysoroban import ArtifactError, compile_source, inspect_wasm, validate_wasm


VECTOR_SOURCE = """
from pysoroban import Vec, contract, i32, public

@contract
class Vectors:
    @public
    def first(self, values: Vec[i32]) -> i32:
        return values[0]

    @public
    def count(self, values: Vec[i32]) -> i32:
        return len(values)
"""


class ArtifactTests(unittest.TestCase):
    def test_inspects_compiled_contract_spec_imports_and_exports(self):
        wasm = compile_source(VECTOR_SOURCE).wasm
        result = inspect_wasm(wasm)

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["contract"], "Vectors")
        self.assertEqual(result["source_lang"], "pysoroban")
        self.assertEqual(result["protocol"], 25)
        self.assertEqual(result["size"], len(wasm))
        self.assertEqual([item["name"] for item in result["functions"]], ["first", "count"])
        self.assertEqual(result["functions"][0]["inputs"][0]["type"], "Vec[i32]")
        self.assertEqual(result["functions"][0]["outputs"], ["i32"])
        self.assertIn(
            {"module": "v", "name": "1", "kind": "function", "type_index": 1},
            result["imports"],
        )
        self.assertEqual(
            [item["name"] for item in result["exports"]],
            ["first", "count", "memory"],
        )
        self.assertEqual(
            [item["name"] for item in result["custom_sections"]],
            ["contractenvmetav0", "contractspecv0", "contractmetav0"],
        )

    def test_inspects_typed_event_spec(self):
        source = """
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
        event = inspect_wasm(compile_source(source).wasm)["events"][0]
        self.assertEqual(event["name"], "Updated")
        self.assertEqual(event["prefix_topics"], ["updated"])
        self.assertEqual(event["topics"][0]["type"], "Address")
        self.assertEqual(event["data"][0]["type"], "u64")

    def test_rejects_non_wasm_missing_soroban_sections_and_truncation(self):
        with self.assertRaisesRegex(ArtifactError, "not a WebAssembly"):
            validate_wasm(b"not wasm")
        with self.assertRaisesRegex(ArtifactError, "missing"):
            validate_wasm(b"\x00asm\x01\x00\x00\x00")

        wasm = compile_source(VECTOR_SOURCE).wasm
        with self.assertRaisesRegex(ArtifactError, "truncated"):
            validate_wasm(wasm[:-1])


if __name__ == "__main__":
    unittest.main()
