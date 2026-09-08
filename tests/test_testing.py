import unittest
from pathlib import Path

from pysoroban.testing import AuthorizationError, ContractTest, Event, InvocationError, StorageMissingError


ROOT = Path(__file__).resolve().parents[1]


class ContractTestTests(unittest.TestCase):
    def test_invokes_math_with_positional_and_keyword_arguments(self):
        contract = ContractTest.from_file(ROOT / "examples/math_contract.py")
        self.assertEqual(contract.invoke("add", 7, 35), 42)
        self.assertEqual(contract.invoke("max", left=-9, right=4), 4)
        self.assertFalse(contract.invoke("is_positive", -1))

    def test_rejects_bad_function_arguments(self):
        contract = ContractTest.from_file(ROOT / "examples/math_contract.py")
        with self.assertRaisesRegex(InvocationError, "unknown contract function"):
            contract.invoke("missing")
        with self.assertRaisesRegex(InvocationError, "expects 2 arguments"):
            contract.invoke("add", 1)
        with self.assertRaisesRegex(InvocationError, "not a valid i32"):
            contract.invoke("add", True, 1)

    def test_requires_per_invocation_authorization(self):
        contract = ContractTest.from_file(ROOT / "examples/counter_contract.py")
        with self.assertRaisesRegex(AuthorizationError, "missing authorization"):
            contract.invoke("increment", "alice", 5)
        self.assertEqual(contract.invoke("increment", "alice", 5, auth={"alice"}), 5)
        with self.assertRaises(AuthorizationError):
            contract.invoke("increment", "alice", 1)

    def test_persists_instance_storage_by_key(self):
        contract = ContractTest.from_file(ROOT / "examples/counter_contract.py")
        contract.invoke("increment", "alice", 5, auth={"alice"})
        contract.invoke("increment", "bob", 9, auth={"bob"})
        self.assertEqual(contract.invoke("value", "alice"), 5)
        self.assertEqual(contract.invoke("value", "bob"), 9)
        self.assertEqual(dict(contract.storage), {"alice": 5, "bob": 9})

    def test_records_typed_event_and_large_u64_storage(self):
        contract = ContractTest.from_file(ROOT / "examples/typed_events_contract.py")
        value = 100_000_000_000_000_000
        self.assertEqual(contract.invoke("record", "alice", value, auth={"alice"}), value)
        self.assertEqual(contract.last_events, (Event(("updated", "alice"), value),))
        self.assertEqual(contract.storage["total"], value)

    def test_exposes_string_bytes_and_i64_results(self):
        contract = ContractTest.from_file(ROOT / "examples/typed_events_contract.py")
        self.assertEqual(contract.invoke("offset", -40_000_000_000_000_000), -40_000_000_000_000_007)
        self.assertEqual(contract.invoke("generation"), 2)
        self.assertEqual(contract.invoke("label"), "PySoroban")
        self.assertEqual(contract.invoke("fingerprint"), b"py-soroban")

    def test_integer_arithmetic_matches_wasm_wrapping(self):
        source = '''
from pysoroban import contract, i32, public, u64
@contract
class Wrapping:
    @public
    def signed(self, value: i32) -> i32:
        return value + i32(1)
    @public
    def unsigned(self, value: u64) -> u64:
        return value + u64(1)
'''
        contract = ContractTest.from_source(source)
        self.assertEqual(contract.invoke("signed", 2**31 - 1), -(2**31))
        self.assertEqual(contract.invoke("unsigned", 2**64 - 1), 0)

    def test_executes_wide_integer_boundaries_comparisons_storage_and_events(self):
        contract = ContractTest.from_file(ROOT / "examples/wide_integer_contract.py")
        minimum = -(2**127)
        maximum = 2**128 - 1
        amount = -(2**100)

        self.assertEqual(contract.invoke("echo_i128", minimum), minimum)
        self.assertEqual(contract.invoke("echo_u128", maximum), maximum)
        self.assertEqual(contract.invoke("minimum_i128"), minimum)
        self.assertEqual(contract.invoke("maximum_u128"), maximum)
        self.assertTrue(contract.invoke("less_i128", minimum, -1))
        self.assertTrue(contract.invoke("less_u128", 2**64, maximum))
        self.assertEqual(contract.invoke("echo_i128s", [minimum, 0, 2**127 - 1]), [minimum, 0, 2**127 - 1])
        self.assertEqual(contract.invoke("lookup_u128", {"maximum": maximum}, "maximum"), maximum)
        self.assertEqual(contract.invoke("record", "alice", amount, auth={"alice"}), amount)
        self.assertEqual(contract.storage["alice"], amount)
        self.assertEqual(contract.last_events, (Event(("amount_recorded", "alice"), amount),))

        with self.assertRaisesRegex(InvocationError, "not a valid i128"):
            contract.invoke("echo_i128", 2**127)
        with self.assertRaisesRegex(InvocationError, "not a valid u128"):
            contract.invoke("echo_u128", -1)

    def test_executes_i128_cross_contract_result(self):
        token_source = '''
from pysoroban import Address, contract, i128, public
@contract
class Token:
    @public
    def balance(self, owner: Address) -> i128:
        return i128(1267650600228229401496703205376)
'''
        token = ContractTest.from_source(token_source)
        caller = ContractTest.from_file(ROOT / "examples/wide_integer_contract.py")
        caller.register_contract("token", token)
        self.assertEqual(caller.invoke("remote_balance", "token", "alice"), 2**100)

    def test_unsigned_floor_division_and_zero_divisor(self):
        source = '''
from pysoroban import contract, public, u32, u64
@contract
class Ratio:
    @public
    def ratio32(self, left: u32, right: u32) -> u32:
        return left // right
    @public
    def ratio64(self, left: u64, right: u64) -> u64:
        return left // right
'''
        contract = ContractTest.from_source(source)
        self.assertEqual(contract.invoke("ratio32", 10, 3), 3)
        self.assertEqual(contract.invoke("ratio64", 2**63, 3), 3_074_457_345_618_258_602)
        with self.assertRaisesRegex(InvocationError, "division by zero"):
            contract.invoke("ratio64", 1, 0)

    def test_executes_parameter_bounded_for_ranges(self):
        contract = ContractTest.from_file(ROOT / "examples/math_contract.py")
        self.assertEqual(contract.invoke("sum_to", 10), 45)
        self.assertEqual(contract.invoke("sum_to", 0), 0)
        self.assertEqual(contract.invoke("sum_to", -4), 0)

    def test_links_and_executes_cross_contract_calls(self):
        math = ContractTest.from_file(ROOT / "examples/math_contract.py")
        proxy = ContractTest.from_file(ROOT / "examples/cross_contract.py")
        proxy.register_contract("math", math)
        self.assertEqual(proxy.invoke("add_with", "math", 5, 7), 12)
        self.assertEqual(proxy.invoke("sum_with", "math", 10), 45)

    def test_links_and_executes_void_cross_contract_calls(self):
        recorder_source = '''
from pysoroban import Symbol, contract, public, storage, u64
@contract
class Recorder:
    @public
    def record(self, value: u64) -> None:
        storage.instance.set(Symbol("last"), value)
'''
        caller_source = '''
from pysoroban import Address, Symbol, contract, public, u64
@contract
class Caller:
    @public
    def notify(self, target: Address, value: u64) -> None:
        target.call_void(Symbol("record"), value)
'''
        recorder = ContractTest.from_source(recorder_source)
        caller = ContractTest.from_source(caller_source)
        caller.register_contract("recorder", recorder)

        self.assertIsNone(caller.invoke("notify", "recorder", 42))
        self.assertEqual(recorder.storage["last"], 42)

    def test_rejects_unknown_cross_contract_targets(self):
        proxy = ContractTest.from_file(ROOT / "examples/cross_contract.py")
        with self.assertRaisesRegex(InvocationError, "unregistered contract address"):
            proxy.invoke("add_with", "missing", 5, 7)

    def test_executes_and_validates_typed_vectors(self):
        vectors = ContractTest.from_file(ROOT / "examples/vector_contract.py")
        self.assertEqual(vectors.invoke("count", [3, 5, 8]), 3)
        self.assertEqual(vectors.invoke("first", [3, 5, 8]), 3)
        self.assertEqual(vectors.invoke("sum", [3, 5, 8]), 16)
        self.assertEqual(vectors.invoke("echo", [3, 5, 8]), [3, 5, 8])
        with self.assertRaisesRegex(InvocationError, r"values\[1\] is not a valid i32"):
            vectors.invoke("sum", [3, "bad"])
        with self.assertRaisesRegex(InvocationError, "out of bounds"):
            vectors.invoke("first", [])

    def test_executes_and_validates_typed_maps(self):
        maps = ContractTest.from_file(ROOT / "examples/map_contract.py")
        scores = {"alice": 9, "bob": 12}
        self.assertEqual(maps.invoke("score", scores, "bob"), 12)
        self.assertTrue(maps.invoke("contains", scores, "alice"))
        self.assertFalse(maps.invoke("contains", scores, "carol"))
        self.assertEqual(maps.invoke("count", scores), 2)
        self.assertEqual(maps.invoke("echo", scores), scores)
        with self.assertRaisesRegex(InvocationError, "Map key 'carol' was not found"):
            maps.invoke("score", scores, "carol")
        with self.assertRaisesRegex(InvocationError, "not a valid i32"):
            maps.invoke("count", {"alice": "bad"})

    def test_typed_storage_get_detects_wrong_or_missing_value(self):
        source = '''
from pysoroban import Symbol, contract, public, storage, u64
@contract
class Store:
    @public
    def put_wrong_type(self) -> None:
        storage.instance.set(Symbol("value"), 1)
    @public
    def get(self) -> u64:
        return storage.instance.get_u64(Symbol("value"))
'''
        contract = ContractTest.from_source(source)
        with self.assertRaises(StorageMissingError):
            contract.invoke("get")
        contract.invoke("put_wrong_type")
        with self.assertRaisesRegex(InvocationError, "stored value is i32, not the requested u64"):
            contract.invoke("get")

    def test_clear_events_preserves_storage(self):
        contract = ContractTest.from_file(ROOT / "examples/typed_events_contract.py")
        contract.invoke("record", "alice", 3, auth={"alice"})
        contract.clear_events()
        self.assertEqual(contract.events, ())
        self.assertEqual(contract.storage["total"], 3)


if __name__ == "__main__":
    unittest.main()
