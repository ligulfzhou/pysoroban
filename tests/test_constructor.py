"""Protocol constructor export and test-host creation rules."""

import unittest

from pysoroban import compile_source, validate_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import AuthorizationError, ContractError, ContractTest, Event, InvocationError


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
        with self.assertRaisesRegex(InvocationError, "only at contract creation"):
            contract._invoke("__constructor", (8,), {}, [], [], set())
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

    def test_deploy_with_constructor_runs_once(self):
        factory = ContractTest.from_source(FACTORY)
        child = ContractTest.from_source(CHILD)
        factory.contract_address = "CFACTORY"
        factory.register_wasm(b"hash", child)
        with self.assertRaisesRegex(InvocationError, "has not run"):
            child.invoke("value")
        address = factory.invoke("deploy", b"hash", b"salt", "GADMIN", 7, auth=["GADMIN"])
        deployed = factory.contract_at(address)
        self.assertEqual(deployed.invoke("value"), 7)
        self.assertEqual(deployed.events, (Event(("init",), 7),))
        self.assertEqual(factory.storage["mark"], 7)
        self.assertEqual(factory.events, (Event(("deploying",), 7),))
        self.assertEqual(factory.deployments[-1]["args"], ("GADMIN", 7))
        self.assertIs(deployed, factory._contracts[address])
        self.assertIsNot(deployed, child)
        with self.assertRaisesRegex(InvocationError, "has not run"):
            ContractTest(child.compilation).invoke("value")
        with self.assertRaisesRegex(InvocationError, "already ran"):
            deployed.invoke("__constructor", "GADMIN", 8)
        self.assertEqual(deployed.invoke("value"), 7)
        # The deploying contract is authorized the way a direct caller is.
        other = factory.invoke("deploy", b"hash", b"other", "CFACTORY", 4)
        self.assertEqual(factory.contract_at(other).invoke("value"), 4)

    def test_failed_deploy_rolls_back_and_can_retry(self):
        factory = ContractTest.from_source(FACTORY)
        child = ContractTest.from_source(CHILD)
        factory.register_wasm(b"hash", child)
        factory.invoke("note")
        with self.assertRaises(AuthorizationError):
            factory.invoke("deploy", b"hash", b"salt", "GADMIN", 7)
        self._assert_failed_deploy_left_factory(factory)
        with self.assertRaisesRegex(InvocationError, "has not run"):
            child.invoke("value")
        address = factory.invoke("deploy", b"hash", b"salt", "GADMIN", 7, auth=["GADMIN"])
        self.assertEqual(factory.contract_at(address).invoke("value"), 7)
        self.assertEqual(factory.storage["kept"], 1)

        factory = ContractTest.from_source(FACTORY)
        broken = ContractTest.from_source(BROKEN)
        factory.register_wasm(b"hash", broken)
        factory.invoke("note")
        created = []
        real_init = ContractTest.__init__

        def spy(this, compilation):
            real_init(this, compilation)
            created.append(this)

        ContractTest.__init__ = spy
        try:
            with self.assertRaises(ContractError):
                factory.invoke("deploy_broken", b"hash", b"salt", 9)
        finally:
            ContractTest.__init__ = real_init
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0]._constructed)
        self.assertEqual(dict(created[0].storage), {})
        self.assertEqual(created[0].events, ())
        self._assert_failed_deploy_left_factory(factory)

    def test_later_failure_rolls_back_a_successful_constructor(self):
        factory = ContractTest.from_source(FACTORY)
        child = ContractTest.from_source(CHILD)
        factory.register_wasm(b"hash", child)
        factory.invoke("note")
        created = []
        real_init = ContractTest.__init__

        def spy(this, compilation):
            real_init(this, compilation)
            created.append(this)

        ContractTest.__init__ = spy
        try:
            with self.assertRaises(ContractError):
                factory.invoke("deploy_then_fail", b"hash", b"salt", "GADMIN", 6, auth=["GADMIN"])
        finally:
            ContractTest.__init__ = real_init
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0]._constructed)
        self.assertEqual(dict(created[0].storage), {})
        self.assertEqual(created[0].events, ())
        self._assert_failed_deploy_left_factory(factory)
        with self.assertRaisesRegex(InvocationError, "unregistered"):
            factory.contract_at(created[0].contract_address)
        address = factory.invoke("deploy", b"hash", b"salt", "GADMIN", 6, auth=["GADMIN"])
        self.assertEqual(factory.contract_at(address).invoke("value"), 6)

    def test_unknown_wasm_records_nothing_and_plain_deploy_stays_recorded(self):
        factory = ContractTest.from_source(FACTORY)
        factory.invoke("note")
        with self.assertRaisesRegex(InvocationError, "unknown Wasm hash"):
            factory.invoke("deploy", b"missing", b"salt", "GADMIN", 7, auth=["GADMIN"])
        self._assert_failed_deploy_left_factory(factory)
        plain = ContractTest.from_source(PLAIN)
        factory.register_wasm(b"plain", plain)
        with self.assertRaisesRegex(InvocationError, "no __constructor"):
            factory.invoke("deploy", b"plain", b"salt", "GADMIN", 1, auth=["GADMIN"])
        self._assert_failed_deploy_left_factory(factory)
        recorded = factory.invoke("install", b"plain", b"salt")
        self.assertEqual(factory.deployments, [{
            "address": recorded,
            "wasm_hash": b"plain",
            "salt": b"salt",
            "args": (),
        }])
        with self.assertRaisesRegex(InvocationError, "unregistered"):
            factory.contract_at(recorded)
        self.assertEqual(factory.storage["kept"], 1)

    def test_duplicate_salt_is_rejected(self):
        factory = ContractTest.from_source(FACTORY)
        factory.register_wasm(b"hash", ContractTest.from_source(CHILD))
        address = factory.invoke("deploy", b"hash", b"salt", "GADMIN", 7, auth=["GADMIN"])
        with self.assertRaisesRegex(InvocationError, "contract already exists"):
            factory.invoke("deploy", b"hash", b"salt", "GADMIN", 7, auth=["GADMIN"])
        self.assertEqual(len(factory.deployments), 1)
        self.assertEqual(factory.contract_at(address).invoke("value"), 7)

    def test_try_call_rolls_back_only_the_failed_deploy(self):
        caller = ContractTest.from_source(CALLER)
        factory = ContractTest.from_source(FACTORY)
        factory.contract_address = "CFACTORY"
        factory.register_wasm(b"hash", ContractTest.from_source(BROKEN))
        caller.register_contract("CFACTORY", factory)
        self.assertEqual(caller.invoke("go", "CFACTORY", b"hash", b"salt", 3), 5)
        self.assertEqual(caller.storage["caller"], 3)
        self.assertEqual(factory.deployments, [])
        self.assertEqual(dict(factory.storage), {})
        self.assertEqual(factory.events, ())

    def _assert_failed_deploy_left_factory(self, factory: ContractTest):
        self.assertEqual(dict(factory.storage), {"kept": 1})
        self.assertEqual(factory.events, (Event(("kept",), 1),))
        self.assertEqual(factory.deployments, [])
        self.assertEqual(factory._contracts, {})


CHILD = """
from pysoroban import Address, Symbol, contract, events, public, storage, u32

@contract
class Child:
    @public
    def __constructor(self, admin: Address, value: u32) -> None:
        admin.require_auth()
        storage.instance.set(Symbol("v"), value)
        events.publish(Symbol("init"), value)

    @public
    def value(self) -> u32:
        return storage.instance.get_u32(Symbol("v"))
"""

BROKEN = """
from pysoroban import Symbol, contract, error, events, fail, public, storage, u32

@error
class Boom:
    NO = 5

@contract
class Broken:
    @public
    def __constructor(self, value: u32) -> None:
        storage.instance.set(Symbol("v"), value)
        events.publish(Symbol("init"), value)
        fail(Boom.NO)

    @public
    def value(self) -> u32:
        return storage.instance.get_u32(Symbol("v"))
"""

PLAIN = """
from pysoroban import contract, public, u32

@contract
class Plain:
    @public
    def get(self) -> u32:
        return u32(1)
"""

FACTORY = """
from pysoroban import Address, Bytes, Symbol, contract, deploy, error, events, fail, public, storage, u32

@error
class Boom:
    NO = 5

@contract
class Factory:
    @public
    def note(self) -> None:
        storage.instance.set(Symbol("kept"), u32(1))
        events.publish(Symbol("kept"), u32(1))

    @public
    def deploy(self, wasm_hash: Bytes, salt: Bytes, admin: Address, value: u32) -> Address:
        storage.instance.set(Symbol("mark"), value)
        events.publish(Symbol("deploying"), value)
        return deploy.with_constructor(wasm_hash, salt, admin, value)

    @public
    def deploy_broken(self, wasm_hash: Bytes, salt: Bytes, value: u32) -> Address:
        storage.instance.set(Symbol("mark"), value)
        events.publish(Symbol("deploying"), value)
        return deploy.with_constructor(wasm_hash, salt, value)

    @public
    def deploy_then_fail(self, wasm_hash: Bytes, salt: Bytes, admin: Address, value: u32) -> Address:
        storage.instance.set(Symbol("mark"), value)
        created: Address = deploy.with_constructor(wasm_hash, salt, admin, value)
        fail(Boom.NO)
        return created

    @public
    def install(self, wasm_hash: Bytes, salt: Bytes) -> Address:
        return deploy.contract(wasm_hash, salt)
"""

CALLER = """
from pysoroban import Address, Bytes, Result, Symbol, contract, public, storage, u32

@contract
class Caller:
    @public
    def go(self, factory: Address, wasm_hash: Bytes, salt: Bytes, value: u32) -> u32:
        storage.instance.set(Symbol("caller"), value)
        caught: Result[Address, u32] = factory.try_address(Symbol("deploy_broken"), wasm_hash, salt, value)
        if caught.is_ok():
            return u32(0)
        return caught.unwrap_err()
"""
