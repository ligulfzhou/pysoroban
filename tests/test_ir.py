import unittest

from pysoroban import compile_source
from pysoroban import ir
from pysoroban.model import Parameter, ValueType


class TypedIRTests(unittest.TestCase):
    def test_lowers_control_flow_and_types_before_wasm(self):
        source = """
from pysoroban import boolean, contract, i32, public

@contract
class Select:
    @public
    def choose(self, flag: boolean, left: i32, right: i32) -> i32:
        result: i32 = right
        if flag:
            result = left
        return result
"""
        result = compile_source(source)
        function = result.ir.functions[0]

        self.assertEqual(function.name, "choose")
        self.assertEqual(function.result, ValueType.I32)
        self.assertEqual(function.locals, (Parameter("result", ValueType.I32),))
        self.assertIsInstance(function.body[0], ir.SetLocal)
        self.assertIsInstance(function.body[1], ir.If)
        self.assertIsInstance(function.body[2], ir.Return)

    def test_lowers_storage_to_explicit_host_operations(self):
        source = """
from pysoroban import Address, contract, i32, public, storage

@contract
class Value:
    @public
    def set(self, owner: Address, value: i32) -> None:
        owner.require_auth()
        storage.instance.set(owner, value)
"""
        body = compile_source(source).ir.functions[0].body
        self.assertEqual(body[0].value.op, "require_auth")
        self.assertEqual(body[1].value.op, "storage_set")

    def test_lowers_typed_literals_and_events(self):
        source = '''
from pysoroban import Symbol, contract, events, public, u64
@contract
class Event:
    @public
    def publish(self) -> u64:
        value: u64 = u64(18446744073709551615)
        events.publish(Symbol("max"), value)
        return value
'''
        body = compile_source(source).ir.functions[0].body
        self.assertEqual(body[0].value.type, ValueType.U64)
        self.assertEqual(body[0].value.value, 2**64 - 1)
        self.assertEqual(body[1].value.op, "event_publish")
        self.assertEqual(body[1].value.args[0].type, ValueType.SYMBOL)

    def test_lowers_typed_event_to_prefix_dynamic_topics_and_data(self):
        source = '''
from pysoroban import Address, Topic, contract, event, events, public, u64
@event
class Updated:
    owner: Topic[Address]
    value: u64
@contract
class C:
    @public
    def emit(self, owner: Address, value: u64) -> None:
        events.publish(Updated(owner, value))
'''
        call = compile_source(source).ir.functions[0].body[0].value
        self.assertEqual(call.op, "event_publish")
        self.assertEqual([arg.type for arg in call.args], [ValueType.SYMBOL, ValueType.ADDRESS, ValueType.U64])
        self.assertEqual(call.args[0].value, "updated")

    def test_lowers_for_range_without_unrolling(self):
        source = '''
from pysoroban import contract, i32, public
@contract
class Loops:
    @public
    def sum_from(self, start: i32, stop: i32) -> i32:
        total: i32 = 0
        for value in range(start, stop):
            total = total + value
        return total
'''
        function = compile_source(source).ir.functions[0]
        loop = function.body[1]
        self.assertIsInstance(loop, ir.ForRange)
        self.assertEqual(loop.variable, "value")
        self.assertEqual(len(loop.body), 1)

    def test_lowers_cross_contract_call_with_explicit_result_type(self):
        source = '''
from pysoroban import Address, Symbol, contract, public, u64
@contract
class Proxy:
    @public
    def balance(self, target: Address, owner: Address) -> u64:
        return target.call_u64(Symbol("balance"), owner)
'''
        call = compile_source(source).ir.functions[0].body[0].value
        self.assertEqual(call.op, "contract_call")
        self.assertEqual(call.type, ValueType.U64)
        self.assertEqual([arg.type for arg in call.args], [ValueType.ADDRESS, ValueType.SYMBOL, ValueType.ADDRESS])

    def test_lowers_vec_access_to_typed_host_calls(self):
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
'''
        result = compile_source(source).ir
        self.assertEqual(result.functions[0].body[0].value.op, "vec_get")
        self.assertEqual(result.functions[0].body[0].value.type, ValueType.I32)
        self.assertEqual(result.functions[1].body[0].value.op, "vec_len")


if __name__ == "__main__":
    unittest.main()
