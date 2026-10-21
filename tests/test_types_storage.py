"""Structs, enums, collection updates, and storage tiers."""

import unittest

from pysoroban import compile_source, inspect_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import ContractTest, StorageMissingError


SOURCE = """
from pysoroban import (
    Address, Map, Symbol, Vec, boolean, contract, enum, i32, public, storage, struct, u32,
)


@struct
class User:
    id: u32
    admin: Address


@enum
class Color:
    RED = 0
    GREEN = 2
    BLUE = 4294967295


@contract
class Registry:
    @public
    def save(self, user: User) -> User:
        storage.instance.set(Symbol("user"), user)
        storage.persistent.set(user.admin, user.id)
        values: Vec[u32] = Vec()
        values.push(user.id)
        values.push(u32(5))
        values.set(1, u32(9))
        values.insert(0, u32(1))
        dropped: u32 = values.pop()
        values.remove(0)
        storage.instance.set(Symbol("values"), values)
        labels: Map[Symbol, Color] = Map()
        labels.set(Symbol("paint"), Color.BLUE)
        storage.temporary.set(Symbol("paint"), labels)
        storage.persistent.extend_ttl(user.admin, u32(10), u32(100))
        storage.instance.extend_ttl(u32(10), u32(100))
        return user

    @public
    def user(self) -> User:
        return storage.instance.get(Symbol("user"), User)

    @public
    def admin_id(self, admin: Address) -> u32:
        return storage.persistent.get(admin, u32)

    @public
    def first(self) -> u32:
        values: Vec[u32] = storage.instance.get(Symbol("values"), Vec[u32])
        return values[0]

    @public
    def paint(self) -> Color:
        labels: Map[Symbol, Color] = storage.temporary.get(Symbol("paint"), Map[Symbol, Color])
        return labels[Symbol("paint")]

    @public
    def remember(self, admin: Address) -> Address:
        storage.instance.set(Symbol("admin"), admin)
        return storage.instance.get_address(Symbol("admin"))

    @public
    def forget(self, admin: Address) -> boolean:
        storage.persistent.remove(admin)
        return storage.persistent.has(admin)
"""


class TypeStorageTests(unittest.TestCase):
    def test_struct_enum_and_storage_round_trip(self):
        contract = ContractTest.from_source(SOURCE)
        user = contract.invoke("save", {"id": 7, "admin": "GUSER"})
        self.assertEqual(user, {"id": 7, "admin": "GUSER"})
        self.assertEqual(contract.invoke("user"), user)
        self.assertEqual(contract.invoke("admin_id", "GUSER"), 7)
        self.assertEqual(contract.storage["user"], user)
        self.assertEqual(contract.invoke("first"), 7)
        self.assertEqual(contract.invoke("paint"), 2**32 - 1)
        self.assertEqual(contract.persistent["GUSER"], 7)
        self.assertEqual(contract.invoke("remember", "GUSER"), "GUSER")
        self.assertFalse(contract.invoke("forget", "GUSER"))
        self.assertNotIn("GUSER", contract.persistent)
        self.assertEqual(contract.ttl_extensions[0]["tier"], "persistent")
        self.assertEqual(contract.ttl_extensions[1]["tier"], "instance")

    def test_spec_records_struct_and_enum(self):
        inspected = inspect_wasm(compile_source(SOURCE).wasm)
        self.assertEqual(inspected["structs"][0]["name"], "User")
        self.assertEqual(inspected["structs"][0]["fields"][1]["type"], "Address")
        self.assertEqual(inspected["enums"][0]["cases"][2]["value"], 2**32 - 1)
        self.assertEqual(inspected["functions"][0]["inputs"][0]["type"], "User")
        imported = {f"{item['module']}.{item['name']}" for item in inspected["imports"]}
        self.assertIn("m._", imported)
        self.assertIn("m.0", imported)
        self.assertIn("l.2", imported)
        self.assertIn("l.7", imported)
        self.assertIn("l.8", imported)
        self.assertIn("v.6", imported)
        self.assertIn("v.7", imported)

    def test_missing_key_and_rejected_recursion(self):
        contract = ContractTest.from_source(SOURCE)
        with self.assertRaises(StorageMissingError):
            contract.invoke("user")
        with self.assertRaises(CompileError) as caught:
            compile_source(
                """
from pysoroban import contract, i32, public, struct

@struct
class Node:
    value: i32
    child: Node

@contract
class Bad:
    @public
    def id(self, node: Node) -> i32:
        return node.value
"""
            )
        self.assertEqual(caught.exception.code, "E0817")

    def test_pop_and_rollback(self):
        source = """
from pysoroban import Vec, contract, error, fail, i32, public, storage

@error
class Oops:
    NO = 1

@contract
class Bag:
    @public
    def grow(self, flag: i32, item: i32) -> i32:
        values: Vec[i32] = Vec()
        if storage.temporary.has(1):
            values = storage.temporary.get(1, Vec[i32])
        values.push(item)
        last: i32 = values.pop()
        values.push(item)
        storage.temporary.set(1, values)
        if flag == 0:
            fail(Oops.NO)
        return last
"""
        contract = ContractTest.from_source(source)
        self.assertEqual(contract.invoke("grow", 1, 3), 3)
        self.assertEqual(list(contract.temporary.values()), [[3]])
        from pysoroban.testing import ContractError
        with self.assertRaises(ContractError):
            contract.invoke("grow", 0, 9)
        self.assertEqual(list(contract.temporary.values()), [[3]])


if __name__ == "__main__":
    unittest.main()
