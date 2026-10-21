"""Option, Result, tuples, unions, nested collections, and try_call."""

import unittest

from pysoroban import compile_source, inspect_wasm, validate_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import ContractError, ContractTest, InvocationError


SUM = """
from pysoroban import (
    Address, Map, Option, Result, Symbol, Tuple, Vec, contract, error, fail,
    public, storage, union, u32,
)


@error
class Boom:
    NO = 9


@union
class DataKey:
    root: None
    claimed: u32


@contract
class Sums:
    @public
    def echo_option(self, value: Option[u32]) -> Option[u32]:
        return value

    @public
    def none(self) -> Option[u32]:
        missing: Option[u32] = Option.none()
        return missing

    @public
    def present(self, value: u32) -> u32:
        wrapped: Option[u32] = Option.some(value)
        if wrapped.is_some():
            return wrapped.unwrap()
        return u32(0)

    @public
    def odd(self, value: u32) -> Result[u32, u32]:
        half: u32 = value // u32(2)
        if half * u32(2) == value:
            return Result[u32, u32].err(Boom.NO)
        return Result[u32, u32].ok(value)

    @public
    def code_of(self, value: u32) -> u32:
        result: Result[u32, u32] = Result[u32, u32].ok(value)
        if value == u32(0):
            result = Result[u32, u32].err(Boom.NO)
        if result.is_ok():
            return result.unwrap()
        return result.unwrap_err()

    @public
    def pair(self, left: Symbol, right: u32) -> u32:
        built: Tuple[Symbol, u32] = Tuple[Symbol, u32](left, right)
        return built[1]

    @public
    def tag(self, value: u32) -> u32:
        key: DataKey = DataKey.root()
        if value == u32(0):
            if key.is_root():
                return u32(1)
            return u32(0)
        key = DataKey.claimed(value)
        if key.is_claimed():
            return key.unwrap_claimed()
        return u32(0)

    @public
    def nested(self) -> u32:
        row: Vec[u32] = Vec()
        row.push(u32(4))
        rows: Vec[Vec[u32]] = Vec()
        rows.push(row)
        table: Map[u32, Vec[u32]] = Map()
        table.set(u32(1), row)
        outer: Vec[u32] = rows[0]
        found: Vec[u32] = table[u32(1)]
        storage.instance.set(Symbol("row"), row)
        return outer[0] + found[0]

    @public
    def stored_row(self) -> u32:
        row: Vec[u32] = storage.instance.get(Symbol("row"), Vec[u32])
        return row[0]
"""


CALLEE = """
from pysoroban import contract, error, fail, public, storage, u32


@error
class Boom:
    NO = 9


@contract
class Callee:
    @public
    def add(self, value: u32) -> u32:
        return value + u32(1)

    @public
    def set_then_fail(self, value: u32) -> u32:
        storage.instance.set(u32(1), value)
        fail(Boom.NO)
        return value
"""


CALLER = """
from pysoroban import Address, Result, Symbol, contract, public, u32


@contract
class Caller:
    @public
    def probe(self, other: Address) -> u32:
        caught: Result[u32, u32] = other.try_u32(Symbol("add"), u32(6))
        if caught.is_ok():
            return caught.unwrap()
        return caught.unwrap_err()

    @public
    def recover(self, other: Address) -> u32:
        caught: Result[u32, u32] = other.try_u32(Symbol("set_then_fail"), u32(5))
        if caught.is_ok():
            return caught.unwrap()
        return caught.unwrap_err()
"""


class SumTypeTests(unittest.TestCase):
    def test_option_result_tuple_union_and_nested_collections(self):
        contract = ContractTest.from_source(SUM)
        self.assertIsNone(contract.invoke("echo_option", None))
        self.assertEqual(contract.invoke("echo_option", 4), 4)
        self.assertIsNone(contract.invoke("none"))
        self.assertEqual(contract.invoke("present", 6), 6)
        self.assertEqual(contract.invoke("odd", 3), ("ok", 3))
        self.assertEqual(contract.invoke("odd", 4), ("err", 9))
        self.assertEqual(contract.invoke("code_of", 8), 8)
        self.assertEqual(contract.invoke("code_of", 0), 9)
        self.assertEqual(contract.invoke("pair", "leaf", 3), 3)
        self.assertEqual(contract.invoke("tag", 0), 1)
        self.assertEqual(contract.invoke("tag", 12), 12)
        self.assertEqual(contract.invoke("nested"), 8)
        self.assertEqual(contract.invoke("stored_row"), 4)

        wasm = compile_source(SUM).wasm
        validate_wasm(wasm)
        self.assertIn(b"\x01d\x010", compile_source(CALLER).wasm)
        inspected = inspect_wasm(wasm)
        names = {item["name"] for item in inspected["functions"]}
        option = next(item for item in inspected["functions"] if item["name"] == "echo_option")
        self.assertEqual(option["outputs"], ["Option[u32]"])
        odd = next(item for item in inspected["functions"] if item["name"] == "odd")
        self.assertEqual(odd["outputs"], ["Result[u32, u32]"])
        self.assertIn("tag", names)
        self.assertIn("DataKey", {item["name"] for item in inspected["enums"]})

    def test_try_call_returns_the_error_and_rolls_the_callee_back(self):
        callee = ContractTest.from_source(CALLEE)
        callee.contract_address = "CCALLEE"
        caller = ContractTest.from_source(CALLER)
        caller.register_contract("CCALLEE", callee)
        self.assertEqual(caller.invoke("probe", "CCALLEE"), 7)
        self.assertEqual(caller.invoke("recover", "CCALLEE"), 9)
        self.assertNotIn(1, callee.storage)
        with self.assertRaises(ContractError):
            callee.invoke("set_then_fail", 5)
        self.assertNotIn(1, callee.storage)

    def test_rejects_bad_sum_shapes(self):
        with self.assertRaises(CompileError) as caught:
            compile_source(
                """
from pysoroban import Option, contract, public, u32

@contract
class Bad:
    @public
    def missing(self) -> u32:
        value = Option.none()
        return u32(1)
"""
            )
        self.assertEqual(caught.exception.code, "E0661")
        with self.assertRaises(CompileError) as caught:
            compile_source(
                """
from pysoroban import Map, Vec, contract, public, u32

@contract
class Bad:
    @public
    def keyed(self, values: Map[Vec[u32], u32]) -> u32:
        return u32(1)
"""
            )
        self.assertEqual(caught.exception.code, "E0204")
        bad = ContractTest.from_source(
            """
from pysoroban import contract, public, union, u32

@union
class DataKey:
    root: None
    claimed: u32

@contract
class Bad:
    @public
    def open(self) -> u32:
        key: DataKey = DataKey.root()
        return key.unwrap_claimed()
"""
        )
        with self.assertRaises(InvocationError):
            bad.invoke("open")


if __name__ == "__main__":
    unittest.main()
