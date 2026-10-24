import unittest

from pysoroban import compile_source, inspect_wasm
from pysoroban.errors import CompileError
from pysoroban.model import ValueType
from pysoroban.scval import xdr_bytes
from pysoroban.testing import ContractTest, InvocationError


SOURCE = """
from pysoroban import Bytes, Symbol, Vec, boolean, contract, i256, public, storage

@contract
class Signed:
    @public
    def add(self, left: i256, right: i256) -> i256:
        return left + right

    @public
    def sub(self, left: i256, right: i256) -> i256:
        return left - right

    @public
    def mul(self, left: i256, right: i256) -> i256:
        return left * right

    @public
    def div(self, left: i256, right: i256) -> i256:
        return left // right

    @public
    def less(self, left: i256, right: i256) -> boolean:
        return left < right

    @public
    def minimum(self) -> i256:
        return i256(-(2 ** 255))

    @public
    def maximum(self) -> i256:
        return i256(2 ** 255 - 1)

    @public
    def be(self, value: i256) -> Bytes:
        return value.to_be_bytes()

    @public
    def parsed(self, data: Bytes) -> i256:
        return i256.from_be_bytes(data)

    @public
    def remember(self, value: i256) -> i256:
        storage.instance.set(Symbol("n"), value)
        return storage.instance.get_i256(Symbol("n"))

    @public
    def echo(self, values: Vec[i256]) -> Vec[i256]:
        return values
"""


class I256Tests(unittest.TestCase):
    def setUp(self):
        self.compiled = compile_source(SOURCE)
        self.contract = ContractTest(self.compiled)

    def test_checked_arithmetic_matches_python_floor_division(self):
        minimum = -(2**255)
        maximum = 2**255 - 1
        self.assertEqual(self.contract.invoke("add", -(2**200), 2**100), -(2**200) + 2**100)
        self.assertEqual(self.contract.invoke("sub", minimum, -1), minimum + 1)
        self.assertEqual(self.contract.invoke("mul", -(2**80), 2**40), -(2**120))
        self.assertEqual(self.contract.invoke("div", -(2**80), -(2**20)), 2**60)
        self.assertEqual(self.contract.invoke("div", -7, 3), -3)
        self.assertEqual(self.contract.invoke("div", 7, -3), -3)
        self.assertEqual(self.contract.invoke("div", -7, -3), 2)
        self.assertTrue(self.contract.invoke("less", -1, 1))
        self.assertFalse(self.contract.invoke("less", maximum, minimum))
        self.assertEqual(self.contract.invoke("minimum"), minimum)
        self.assertEqual(self.contract.invoke("maximum"), maximum)

    def test_overflow_and_division_by_zero_trap(self):
        minimum = -(2**255)
        for name, args in (
            ("add", (2**255 - 1, 1)),
            ("sub", (minimum, 1)),
            ("mul", (2**200, 2**200)),
            ("div", (minimum, -1)),
        ):
            with self.assertRaisesRegex(InvocationError, "i256 arithmetic overflow"):
                self.contract.invoke(name, *args)
        with self.assertRaisesRegex(InvocationError, "division by zero"):
            self.contract.invoke("div", 1, 0)

    def test_bytes_storage_vector_and_spec(self):
        negative = b"\xff" * 32
        self.assertEqual(self.contract.invoke("parsed", negative), -1)
        with self.assertRaisesRegex(InvocationError, "requires 32 bytes"):
            self.contract.invoke("parsed", b"\xff")
        self.assertEqual(self.contract.invoke("be", -1), negative)
        self.assertEqual(self.contract.invoke("be", -(2**255)), b"\x80" + b"\x00" * 31)
        self.assertEqual(self.contract.invoke("remember", -9), -9)
        self.assertEqual(self.contract.invoke("echo", [-4, 0, 2**200]), [-4, 0, 2**200])
        self.assertEqual(
            xdr_bytes(-1, ValueType.I256).hex(),
            "0000000c" + "ff" * 32,
        )
        inspected = inspect_wasm(self.compiled.wasm)
        parsed = next(item for item in inspected["functions"] if item["name"] == "parsed")
        self.assertEqual(parsed["inputs"][0]["type"], "Bytes")
        self.assertEqual(parsed["outputs"], ["i256"])
        with self.assertRaisesRegex(CompileError, "outside the i256 range"):
            compile_source(
                "from pysoroban import contract, i256, public\n"
                "@contract\nclass T:\n    @public\n    def n(self) -> i256:\n"
                "        return i256(2 ** 255)\n"
            )
        with self.assertRaisesRegex(CompileError, "invalid unary operator"):
            compile_source(
                "from pysoroban import contract, i256, public\n"
                "@contract\nclass T:\n    @public\n    def n(self, value: i256) -> i256:\n"
                "        return -value\n"
            )
