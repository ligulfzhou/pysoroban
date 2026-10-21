"""Protocol constructor export and test-host creation rules."""

import unittest

from pysoroban import compile_source, validate_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import ContractTest, InvocationError


class ConstructorTests(unittest.TestCase):
    def test_constructor_runs_once_and_is_exported(self):
        contract = ContractTest.from_source(
            """
from pysoroban import contract, public, storage, Symbol, u32

@contract
class Box:
    @public
    def __constructor(self, value: u32) -> None:
        storage.instance.set(Symbol("v"), value)

    @public
    def get(self) -> u32:
        return storage.instance.get_u32(Symbol("v"))
"""
        )
        with self.assertRaisesRegex(InvocationError, "has not run"):
            contract.invoke("get")
        contract.invoke("__constructor", 7)
        self.assertEqual(contract.invoke("get"), 7)
        with self.assertRaisesRegex(InvocationError, "already ran"):
            contract.invoke("__constructor", 8)
        self.assertEqual(contract.invoke("get"), 7)
        wasm = contract.compilation.wasm
        validate_wasm(wasm)
        self.assertIn(b"__constructor", wasm)

    def test_failed_constructor_can_be_retried(self):
        contract = ContractTest.from_source(
            """
from pysoroban import Address, contract, public

@contract
class Gate:
    @public
    def __constructor(self, admin: Address) -> None:
        admin.require_auth()
"""
        )
        with self.assertRaises(InvocationError):
            contract.invoke("__constructor", "GADMIN")
        contract.invoke("__constructor", "GADMIN", auth=["GADMIN"])
        self.assertTrue(contract._constructed)

    def test_constructor_must_return_void_and_cannot_be_called(self):
        with self.assertRaisesRegex(CompileError, "must return None"):
            compile_source(
                """
from pysoroban import contract, public, u32

@contract
class Bad:
    @public
    def __constructor(self) -> u32:
        return u32(1)
"""
            )
        with self.assertRaisesRegex(CompileError, "only at contract creation"):
            compile_source(
                """
from pysoroban import Address, Symbol, contract, public

@contract
class Caller:
    @public
    def go(self, other: Address) -> None:
        other.call_void(Symbol("__constructor"))
"""
            )
