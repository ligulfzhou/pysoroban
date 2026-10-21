import unittest

from pysoroban import compile_source, inspect_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import ContractError, ContractTest


GATE = """
from pysoroban import contract, error, fail, i32, public, storage, Symbol

@error
class GateError:
    NOPE = 7

@contract
class Gate:
    @public
    def pick(self, flag: i32, value: i32) -> i32:
        if flag == 0:
            fail(GateError.NOPE)
        return value

    @public
    def write_then_fail(self, value: i32) -> i32:
        storage.instance.set(Symbol("n"), value)
        fail(GateError.NOPE)
        return value
"""

CALLER = """
from pysoroban import Address, Symbol, contract, public, storage, i32

@contract
class Caller:
    @public
    def relay(self, target: Address, value: i32) -> i32:
        storage.instance.set(Symbol("n"), value)
        return target.call_i32(Symbol("pick"), 0, value)
"""

CALLEE = """
from pysoroban import contract, error, fail, i32, public, storage, Symbol

@error
class GateError:
    NOPE = 7

@contract
class Callee:
    @public
    def pick(self, flag: i32, value: i32) -> i32:
        storage.instance.set(Symbol("seen"), value)
        if flag == 0:
            fail(GateError.NOPE)
        return value
"""


class FailureTests(unittest.TestCase):
    def test_fail_traps_and_records_the_spec_case(self):
        compiled = compile_source(GATE, "gate.py")
        inspected = inspect_wasm(compiled.wasm)
        self.assertEqual(inspected["errors"], [{
            "name": "GateError",
            "doc": "",
            "cases": [{"doc": "", "name": "NOPE", "value": 7}],
        }])
        self.assertIn(("x", "5"), {(item["module"], item["name"]) for item in inspected["imports"]})

        gate = ContractTest(compiled)
        self.assertEqual(gate.invoke("pick", 1, 4), 4)
        with self.assertRaises(ContractError) as raised:
            gate.invoke("pick", 0, 4)
        self.assertEqual((raised.exception.error, raised.exception.case, raised.exception.code), ("GateError", "NOPE", 7))

    def test_failure_rolls_back_storage_and_events(self):
        gate = ContractTest.from_source(GATE, "gate.py")
        gate.invoke("pick", 1, 4)
        with self.assertRaises(ContractError):
            gate.invoke("write_then_fail", 9)
        self.assertEqual(dict(gate.storage), {})
        self.assertEqual(gate.events, ())
        self.assertEqual(gate.last_events, ())

    def test_nested_failure_rolls_back_both_contracts(self):
        caller = ContractTest.from_source(CALLER, "caller.py")
        callee = ContractTest.from_source(CALLEE, "callee.py")
        caller.register_contract("other", callee)
        with self.assertRaises(ContractError):
            caller.invoke("relay", "other", 3)
        self.assertEqual(dict(caller.storage), {})
        self.assertEqual(dict(callee.storage), {})

    def test_fail_rejects_bad_cases(self):
        source = """
from pysoroban import contract, error, fail, public

@error
class Broken:
    NOPE = 1

@contract
class Gate:
    @public
    def go(self) -> None:
        fail(Broken.MISSING)
"""
        with self.assertRaises(CompileError) as raised:
            compile_source(source)
        self.assertEqual(raised.exception.code, "E0711")

    def test_published_event_is_discarded_when_the_call_fails(self):
        source = """
from pysoroban import Symbol, contract, error, events, fail, public

@error
class GateError:
    NOPE = 1

@contract
class Gate:
    @public
    def go(self) -> None:
        events.publish(Symbol("tried"), 1)
        fail(GateError.NOPE)
"""
        gate = ContractTest.from_source(source)
        with self.assertRaises(ContractError):
            gate.invoke("go")
        self.assertEqual(gate.events, ())
