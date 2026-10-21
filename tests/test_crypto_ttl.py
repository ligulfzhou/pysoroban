"""Curve host passthrough, real ed25519 checks, and optional TTL expiry."""

import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pysoroban import validate_wasm
from pysoroban.errors import CompileError
from pysoroban.testing import AuthorizationError, ContractError, ContractTest, InvocationError, StorageMissingError


ROOT = "examples/soroban"

TTL = """
from pysoroban import Symbol, boolean, contract, ledger, public, storage, u32

@contract
class Ttl:
    @public
    def put(self) -> None:
        storage.temporary.set(Symbol("k"), u32(1))
        storage.persistent.set(Symbol("k"), u32(2))
        storage.instance.set(Symbol("k"), u32(3))

    @public
    def extend_temp(self, threshold: u32, extend_to: u32) -> None:
        storage.temporary.extend_ttl(Symbol("k"), threshold, extend_to)

    @public
    def extend_instance(self, threshold: u32, extend_to: u32) -> None:
        storage.instance.extend_ttl(threshold, extend_to)

    @public
    def has_temp(self) -> boolean:
        return storage.temporary.has(Symbol("k"))

    @public
    def get_temp(self) -> u32:
        return storage.temporary.get(Symbol("k"), u32)

    @public
    def has_instance(self) -> boolean:
        return storage.instance.has(Symbol("k"))

    @public
    def has_persistent(self) -> boolean:
        return storage.persistent.has(Symbol("k"))

    @public
    def horizon(self) -> u32:
        return ledger.max_live_until()
"""

CURVE = """
from pysoroban import Bytes, Vec, boolean, contract, crypto, public, u256, u64

@contract
class Curve:
    @public
    def add(self, left: Bytes, right: Bytes) -> Bytes:
        return crypto.bn254_g1_add(left, right)

    @public
    def pair(self, left: Vec[Bytes], right: Vec[Bytes]) -> boolean:
        return crypto.bn254_multi_pairing_check(left, right)

    @public
    def pow(self, value: u256, exp: u64) -> u256:
        return crypto.bls12_381_fr_pow(value, exp)
"""

GATE = """
from pysoroban import Bytes, String, contract, crypto, log, public

@contract
class Gate:
    @public
    def enter(self, key: Bytes, message: Bytes, signature: Bytes) -> None:
        log(String("before"))
        crypto.ed25519_verify(key, message, signature)
        log(String("after"))
"""


class CryptoAndTtlTests(unittest.TestCase):
    def test_real_ed25519_signature_needs_no_allow_list(self):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        message = b"payload"
        signature = private.sign(message)
        gate = ContractTest.from_source(GATE)
        gate.invoke("enter", public, message, signature)
        self.assertEqual(gate.logs, ["before", "after"])
        with self.assertRaises(InvocationError):
            gate.invoke("enter", public, message, b"\x00" * 64)
        self.assertEqual(gate.logs, ["before", "after"])

    def test_ttl_expires_only_when_enforced(self):
        ttl = ContractTest.from_source(TTL)
        self.assertEqual(ttl.invoke("horizon"), 2**32 - 1)
        self.assertIn(b"\x01x\x018", ttl.compilation.wasm)
        ttl.invoke("put")
        ttl.invoke("extend_temp", 10, 5)
        ttl.ledger_sequence = 100
        self.assertTrue(ttl.invoke("has_temp"))
        ttl.enforce_ttl = True
        self.assertFalse(ttl.invoke("has_temp"))
        self.assertNotIn("k", ttl.temporary)
        with self.assertRaises(StorageMissingError):
            ttl.invoke("get_temp")
        self.assertTrue(ttl.invoke("has_instance"))
        self.assertTrue(ttl.invoke("has_persistent"))

    def test_ttl_threshold_and_max_live_until(self):
        ttl = ContractTest.from_source(TTL)
        ttl.enforce_ttl = True
        ttl.invoke("put")
        ttl.invoke("extend_temp", 0, 50)
        ttl.invoke("extend_temp", 0, 10)
        ttl.ledger_sequence = 51
        self.assertTrue(ttl.invoke("has_temp"))
        ttl.ledger_sequence = 52
        self.assertFalse(ttl.invoke("has_temp"))
        ttl.ledger_sequence = 1
        ttl.max_live_until_ledger = 8
        self.assertEqual(ttl.invoke("horizon"), 8)
        ttl.invoke("extend_instance", 1, 100)
        ttl.ledger_sequence = 8
        self.assertTrue(ttl.invoke("has_instance"))
        ttl.ledger_sequence = 9
        self.assertFalse(ttl.invoke("has_instance"))
        self.assertEqual(ttl.storage, {})
        self.assertTrue(ttl.invoke("has_persistent"))

    def test_curve_host_returns_the_scripted_value(self):
        curve = ContractTest.from_source(CURVE)
        validate_wasm(curve.compilation.wasm)
        self.assertIn(b"\x01c\x01m", curve.compilation.wasm)
        self.assertIn(b"\x01c\x01o", curve.compilation.wasm)
        self.assertIn(b"\x01c\x01k", curve.compilation.wasm)
        curve.allow_host_result("bn254_g1_add", b"\x01" * 64)
        self.assertEqual(curve.invoke("add", b"\x02" * 64, b"\x03" * 64), b"\x01" * 64)
        curve.allow_host_result("bn254_multi_pairing_check", True)
        self.assertTrue(curve.invoke("pair", [b"\x01" * 64], [b"\x03" * 128]))
        curve.allow_host_result("bls12_381_fr_pow", 9)
        self.assertEqual(curve.invoke("pow", 2, 3), 9)
        with self.assertRaisesRegex(InvocationError, "not evaluated"):
            curve.invoke("add", b"\x02" * 64, b"\x03" * 64)
        with self.assertRaisesRegex(InvocationError, "unknown curve"):
            curve.allow_host_result("bn254_fr_add", 1)

    def test_protocol_26_curve_names_and_oversized_bytesn_are_rejected(self):
        late = """
from pysoroban import contract, crypto, public, u256

@contract
class Late:
    @public
    def add(self, left: u256, right: u256) -> u256:
        return crypto.bn254_fr_add(left, right)
"""
        with self.assertRaisesRegex(CompileError, "unsupported function or method call"):
            ContractTest.from_source(late)
        wide = """
from pysoroban import Bytes, BytesN, contract, public

@contract
class Wide:
    @public
    def echo(self, value: Bytes) -> BytesN[1025]:
        return BytesN[1025](value)
"""
        with self.assertRaisesRegex(CompileError, "1 to 1024"):
            ContractTest.from_source(wide)

    def test_bls_signature_increment_uses_the_scripted_pairing(self):
        account = ContractTest.from_file(f"{ROOT}/bls_signature/contract.py")
        validate_wasm(account.compilation.wasm)
        self.assertIn(b"\x01c\x01f", account.compilation.wasm)
        self.assertIn(b"\x01c\x01g", account.compilation.wasm)
        account.contract_address = "CBLS"
        public = b"\x11" * 96
        account.invoke("initialize", public)
        payload = b"\x22" * 32
        signature = b"\x33" * 192
        account.allow_host_result("bls12_381_hash_to_g2", b"\x44" * 192)
        account.allow_host_result("bls12_381_multi_pairing_check", True)
        account.authorize_account("CBLS", payload, signature)
        self.assertEqual(account.invoke("increment"), 1)
        self.assertEqual(account.persistent[("union", "Owners", ())], public)
        account.allow_host_result("bls12_381_hash_to_g2", b"\x44" * 192)
        account.allow_host_result("bls12_381_multi_pairing_check", False)
        account.authorize_account("CBLS", payload, signature)
        with self.assertRaises(AuthorizationError) as caught:
            account.invoke("increment")
        self.assertIsInstance(caught.exception.__cause__, ContractError)
        self.assertEqual(caught.exception.__cause__.code, 1)
        self.assertEqual(account.storage[("union", "Counter", ())], 1)
        self.assertEqual(account._host_results["bls12_381_multi_pairing_check"], [False])
