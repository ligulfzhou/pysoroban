import base64
import unittest

from pysoroban import compile_source
from pysoroban.errors import CompileError


SOURCE = """
from pysoroban import boolean, contract, i32, public

@contract
class Math:
    @public
    def add(self, a: i32, b: i32) -> i32:
        return a + b

    @public
    def choose(self, flag: boolean, a: i32, b: i32) -> i32:
        if flag:
            result: i32 = a
        else:
            result: i32 = b
        return result
"""


class CompilerTests(unittest.TestCase):
    def test_emits_wasm_and_soroban_sections(self):
        result = compile_source(SOURCE)
        self.assertEqual(result.wasm[:8], b"\x00asm\x01\x00\x00\x00")
        self.assertIn(b"contractenvmetav0", result.wasm)
        self.assertIn(b"contractspecv0", result.wasm)
        self.assertIn(b"contractmetav0", result.wasm)
        self.assertEqual([fn.name for fn in result.contract.functions], ["add", "choose"])

    def test_build_is_deterministic(self):
        first = compile_source(SOURCE).wasm
        second = compile_source(SOURCE).wasm
        self.assertEqual(base64.b64encode(first), base64.b64encode(second))

    def test_rejects_dynamic_python(self):
        source = """
from pysoroban import contract, i32, public
@contract
class Bad:
    @public
    def value(self, x: i32) -> i32:
        return str(x)
"""
        with self.assertRaisesRegex(CompileError, "unsupported function or method call"):
            compile_source(source)

    def test_requires_return_on_all_paths(self):
        source = """
from pysoroban import contract, i32, public
@contract
class Bad:
    @public
    def value(self, x: i32) -> i32:
        if x > 0:
            return x
"""
        with self.assertRaisesRegex(CompileError, "does not return on every path"):
            compile_source(source)

    def test_rejects_unimplemented_python_floor_division(self):
        source = """
from pysoroban import contract, i32, public
@contract
class Bad:
    @public
    def value(self, x: i32) -> i32:
        return x // 2
"""
        with self.assertRaisesRegex(CompileError, "supported arithmetic operators"):
            compile_source(source)

    def test_compiles_storage_and_auth_imports(self):
        source = """
from pysoroban import Address, contract, i32, public, storage
@contract
class Counter:
    @public
    def increment(self, admin: Address, amount: i32) -> i32:
        admin.require_auth()
        current: i32 = storage.instance.get_i32(1)
        current = current + amount
        storage.instance.set(1, current)
        return current
"""
        wasm = compile_source(source).wasm
        self.assertIn(b"\x01l\x01_", wasm)
        self.assertIn(b"\x01a\x010", wasm)


if __name__ == "__main__":
    unittest.main()
