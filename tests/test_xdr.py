import unittest

from pysoroban import compile_source
from pysoroban.model import ValueType
from pysoroban.scval import xdr_bytes
from pysoroban.testing import ContractTest, InvocationError


class ScValEncoderTests(unittest.TestCase):
    def test_matches_stellar_sdk_samples(self):
        samples = {
            (True, ValueType.BOOL): "0000000000000001",
            (7, ValueType.U32): "0000000300000007",
            (-3, ValueType.I32): "00000004fffffffd",
            ("index", ValueType.SYMBOL): "0000000f00000005696e646578000000",
            (bytes([1, 2, 3]), ValueType.BYTES): "0000000d0000000301020300",
            (-(2**64) + 5, ValueType.I128): "0000000affffffffffffffff0000000000000005",
            ((1 << 64) + 2, ValueType.U128): "0000000900000000000000010000000000000002",
        }
        for (value, value_type), expected in samples.items():
            self.assertEqual(xdr_bytes(value, value_type).hex(), expected)

    def test_contract_orders_bytes_and_checks_length(self):
        source = """
from pysoroban import Address, Bytes, BytesN, String, boolean, contract, public, to_xdr, u256

@contract
class Codec:
    @public
    def before(self, left: Bytes, right: Bytes) -> boolean:
        return left < right

    @public
    def encoded(self, value: u256) -> Bytes:
        return to_xdr(value)

    @public
    def be(self, value: u256) -> Bytes:
        return value.to_be_bytes()

    @public
    def parsed(self, data: Bytes) -> u256:
        return u256.from_be_bytes(data)

    @public
    def fixed(self, data: Bytes) -> BytesN[4]:
        return BytesN[4](data)

    @public
    def strkey(self, address: Address) -> String:
        return address.to_strkey()
"""
        contract = ContractTest(compile_source(source))
        self.assertTrue(contract.invoke("before", b"\x01", b"\x02"))
        self.assertFalse(contract.invoke("before", b"\x02", b"\x01"))
        self.assertEqual(contract.invoke("be", 0x0102), b"\x00" * 30 + b"\x01\x02")
        self.assertEqual(contract.invoke("parsed", b"\x01\x02"), 0x0102)
        self.assertEqual(contract.invoke("fixed", b"abcd"), b"abcd")
        self.assertEqual(contract.invoke("strkey", "GABC"), "GABC")
        encoded = contract.invoke("encoded", 7)
        self.assertTrue(encoded.startswith(bytes.fromhex("0000000b")))
        with self.assertRaises(InvocationError):
            contract.invoke("fixed", b"ab")
        self.assertIn(b"\x01b\x01_", contract.compilation.wasm)
