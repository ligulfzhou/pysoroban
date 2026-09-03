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

    def test_compiles_extended_integer_and_object_types(self):
        source = '''
from pysoroban import Bytes, String, Symbol, contract, i64, public, u32, u64
@contract
class Types:
    @public
    def add64(self, left: i64, right: i64) -> i64:
        return left + right
    @public
    def addu64(self, left: u64, right: u64) -> u64:
        return left + right
    @public
    def max32(self, left: u32, right: u32) -> u32:
        if left > right:
            return left
        return right
    @public
    def label(self) -> String:
        return String("PySoroban")
    @public
    def token(self) -> Symbol:
        return Symbol("PY")
    @public
    def raw(self) -> Bytes:
        return Bytes(b"py")
'''
        result = compile_source(source)
        self.assertEqual(
            [function.result.value for function in result.contract.functions],
            ["i64", "u64", "u32", "String", "Symbol", "Bytes"],
        )
        self.assertIn(b"PySoroban", result.wasm)
        self.assertIn(b"\x01i\x01_", result.wasm)
        self.assertIn(b"\x01b\x01i", result.wasm)

    def test_compiles_event_and_extended_storage(self):
        source = '''
from pysoroban import Symbol, contract, events, public, storage, u64
@contract
class Meter:
    @public
    def store(self, value: u64) -> u64:
        key: Symbol = Symbol("total")
        storage.instance.set(key, value)
        events.publish(Symbol("updated"), value)
        return storage.instance.get_u64(key)
'''
        wasm = compile_source(source).wasm
        self.assertIn(b"\x01x\x011", wasm)
        self.assertIn(b"\x01v\x01g", wasm)

    def test_compiles_typed_event_spec_and_dynamic_topics(self):
        source = '''
from pysoroban import Address, Topic, contract, event, events, public, u64
@event
class BalanceUpdated:
    owner: Topic[Address]
    sequence: Topic[u64]
    value: u64
@contract
class Meter:
    @public
    def emit(self, owner: Address, sequence: u64, value: u64) -> None:
        events.publish(BalanceUpdated(owner, sequence, value))
'''
        result = compile_source(source)
        event = result.contract.events[0]
        self.assertEqual((event.name, event.prefix), ("BalanceUpdated", "balance_updated"))
        self.assertEqual([field.topic for field in event.fields], [True, True, False])
        self.assertIn(b"BalanceUpdated", result.wasm)
        self.assertIn(b"balance_updated", result.wasm)

    def test_rejects_invalid_typed_event_shapes_and_calls(self):
        sources = [
            ('''\
from pysoroban import Topic, contract, event, public, u64
@event
class Bad:
    first: u64
    second: u64
@contract
class C:
    @public
    def run(self) -> None:
        pass
''', "exactly one data field"),
            ('''\
from pysoroban import Address, Topic, contract, event, events, public, u64
@event
class Changed:
    owner: Topic[Address]
    value: u64
@contract
class C:
    @public
    def run(self, owner: Address) -> None:
        events.publish(Changed(owner))
''', "expects 2 arguments"),
        ]
        for source, message in sources:
            with self.subTest(message=message):
                with self.assertRaisesRegex(CompileError, message):
                    compile_source(source)

    def test_rejects_out_of_range_integer_constructors(self):
        cases = [
            ("u32", "-1"),
            ("u32", str(2**32)),
            ("i64", str(2**63)),
            ("u64", str(2**64)),
        ]
        for type_name, literal in cases:
            with self.subTest(type_name=type_name, literal=literal):
                source = f'''
from pysoroban import contract, public, {type_name}
@contract
class Bad:
    @public
    def value(self) -> {type_name}:
        return {type_name}({literal})
'''
                with self.assertRaisesRegex(CompileError, "outside the .* range"):
                    compile_source(source)

    def test_requires_explicit_typed_integer_literals(self):
        source = '''
from pysoroban import contract, public, u64
@contract
class Bad:
    @public
    def value(self) -> u64:
        return 1
'''
        with self.assertRaisesRegex(CompileError, "expected return type u64, got i32"):
            compile_source(source)

    def test_rejects_non_symbol_event_topic(self):
        source = '''
from pysoroban import contract, events, i32, public
@contract
class Bad:
    @public
    def emit(self, value: i32) -> None:
        events.publish(value, value)
'''
        with self.assertRaisesRegex(CompileError, "event topic must be a Symbol"):
            compile_source(source)

    def test_rejects_invalid_symbol_characters(self):
        for literal in ["not-valid", "符号", "x" * 33]:
            with self.subTest(literal=literal):
                source = f'''
from pysoroban import Symbol, contract, public
@contract
class Bad:
    @public
    def value(self) -> Symbol:
        return Symbol({literal!r})
'''
                with self.assertRaisesRegex(CompileError, r"\[a-zA-Z0-9_\]"):
                    compile_source(source)

    def test_compiles_for_range_to_wasm_loop(self):
        source = '''
from pysoroban import contract, i32, public
@contract
class Loops:
    @public
    def sum_to(self, stop: i32) -> i32:
        total: i32 = 0
        for value in range(stop):
            total = total + value
        return total
'''
        wasm = compile_source(source).wasm
        self.assertIn(b"\x02\x40\x03\x40", wasm)
        self.assertIn(b"\x0d\x01", wasm)

    def test_rejects_unsupported_range_forms_and_loop_local_declarations(self):
        cases = [
            ("range(0, stop, 2)", "one or two arguments", "total = total + value"),
            ("items", "require range", "total = total + value"),
            ("range(stop)", "declared before", "created: i32 = value"),
        ]
        for iterable, message, body in cases:
            with self.subTest(iterable=iterable):
                source = f'''
from pysoroban import contract, i32, public
@contract
class Bad:
    @public
    def run(self, stop: i32) -> i32:
        total: i32 = 0
        for value in {iterable}:
            {body}
        return total
'''
                with self.assertRaisesRegex(CompileError, message):
                    compile_source(source)

    def test_compiles_statically_typed_cross_contract_calls(self):
        source = '''
from pysoroban import Address, Symbol, contract, i32, public
@contract
class Proxy:
    @public
    def add_with(self, target: Address, left: i32, right: i32) -> i32:
        return target.call_i32(Symbol("add"), left, right)
'''
        wasm = compile_source(source).wasm
        self.assertIn(b"\x01d\x01_", wasm)
        self.assertIn(b"add", wasm)

    def test_contract_call_host_import_is_added_only_when_used(self):
        self.assertNotIn(b"\x01d\x01_", compile_source(SOURCE).wasm)

    def test_compiles_generic_vec_signatures_length_and_indexing(self):
        source = '''
from pysoroban import Vec, contract, i32, public
@contract
class Vectors:
    @public
    def first(self, values: Vec[i32]) -> i32:
        return values[0]
    @public
    def count(self, values: Vec[i32]) -> i32:
        return len(values)
    @public
    def echo(self, values: Vec[i32]) -> Vec[i32]:
        return values
'''
        result = compile_source(source)
        self.assertEqual(result.contract.functions[0].params[0].type.value, "Vec[i32]")
        self.assertEqual(result.contract.functions[2].result.value, "Vec[i32]")
        self.assertIn(b"\x01v\x011", result.wasm)
        self.assertIn(b"\x01v\x013", result.wasm)

    def test_rejects_invalid_vec_annotations_and_indexing(self):
        cases = [
            ("Vec[None]", "None is not valid"),
            ("Vec[Vec[i32]]", "unsupported Vec element type"),
        ]
        for annotation, message in cases:
            with self.subTest(annotation=annotation):
                source = f'''
from pysoroban import Vec, contract, i32, public
@contract
class Bad:
    @public
    def echo(self, value: {annotation}) -> {annotation}:
        return value
'''
                with self.assertRaisesRegex(CompileError, message):
                    compile_source(source)

    def test_rejects_invalid_cross_contract_calls(self):
        cases = [
            ('target.call_i32()', "requires a Symbol"),
            ('target.call_i32(value, value)', "function name must be a Symbol"),
            ('value.call_i32(Symbol("add"), value)', "only available on Address"),
        ]
        for expression, message in cases:
            with self.subTest(expression=expression):
                source = f'''
from pysoroban import Address, Symbol, contract, i32, public
@contract
class Bad:
    @public
    def run(self, target: Address, value: i32) -> i32:
        return {expression}
'''
                with self.assertRaisesRegex(CompileError, message):
                    compile_source(source)


if __name__ == "__main__":
    unittest.main()
