"""Ledger, hashing, bytes, deployment, and checked wide multiplication."""

import unittest

from pysoroban.testing import ContractTest, InvocationError


class HostServiceTests(unittest.TestCase):
    def test_ledger_hash_bytes_and_deploy(self):
        contract = ContractTest.from_source(
            """
from pysoroban import (
    Address, Bytes, String, contract, crypto, deploy, env, i32, ledger, log, prng, public, u32, u64,
)

@contract
class Host:
    @public
    def context(self) -> u64:
        log(String("ready"))
        if ledger.sequence() != u32(1):
            return u64(0)
        return ledger.timestamp()

    @public
    def digest(self, value: Bytes) -> Bytes:
        hashed: Bytes = crypto.sha256(value)
        return hashed.slice(u32(0), u32(2))

    @public
    def join(self, left: Bytes, right: Bytes) -> i32:
        left.append(right)
        return len(left)

    @public
    def install(self, wasm: Bytes, salt: Bytes) -> Address:
        uploaded: Bytes = deploy.upload(wasm)
        return deploy.contract(uploaded, salt)

    @public
    def me(self) -> Address:
        return env.current_contract_address()

    @public
    def roll(self, low: u64, high: u64) -> u64:
        return prng.u64(low, high)
"""
        )
        contract.ledger_timestamp = 42
        self.assertEqual(contract.invoke("context"), 42)
        self.assertEqual(contract.logs, ["ready"])
        digest = contract.invoke("digest", b"abc")
        import hashlib
        self.assertEqual(digest, hashlib.sha256(b"abc").digest()[:2])
        self.assertEqual(contract.invoke("join", b"ab", b"cd"), 4)
        address = contract.invoke("install", b"wasm", b"salt")
        self.assertEqual(address, contract.deployments[-1]["address"])
        self.assertEqual(contract.invoke("me"), "CSELF")
        self.assertEqual(contract.invoke("roll", 5, 5), 5)

    def test_signature_failure_rolls_back_the_log(self):
        contract = ContractTest.from_source(
            """
from pysoroban import Bytes, String, contract, crypto, log, public

@contract
class Gate:
    @public
    def enter(self, key: Bytes, message: Bytes, signature: Bytes) -> None:
        log(String("before"))
        crypto.ed25519_verify(key, message, signature)
        log(String("after"))
"""
        )
        with self.assertRaises(InvocationError):
            contract.invoke("enter", b"key", b"message", b"signature")
        self.assertEqual(contract.logs, [])
        contract.allow_signature(b"key", b"message", b"signature")
        contract.invoke("enter", b"key", b"message", b"signature")
        self.assertEqual(contract.logs, ["before", "after"])

    def test_checked_wide_multiplication_matches_python(self):
        contract = ContractTest.from_source(
            """
from pysoroban import contract, i128, public, u128

@contract
class Math:
    @public
    def mul(self, left: u128, right: u128) -> u128:
        return left * right

    @public
    def div(self, left: u128, right: u128) -> u128:
        return left // right

    @public
    def signed(self, left: i128, right: i128) -> i128:
        return left * right
"""
        )
        self.assertEqual(contract.invoke("mul", 2**100, 2**20), 2**120)
        self.assertEqual(contract.invoke("div", 2**100, 2**20), 2**80)
        self.assertEqual(contract.invoke("signed", -(2**50), -(2**20)), 2**70)
        with self.assertRaises(InvocationError):
            contract.invoke("mul", 2**128 - 1, 2)
        with self.assertRaises(InvocationError):
            contract.invoke("div", 1, 0)


if __name__ == "__main__":
    unittest.main()
