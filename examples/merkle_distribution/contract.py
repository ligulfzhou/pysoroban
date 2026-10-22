"""Merkle token distribution.

The leaf is the XDR of a `Receiver` struct, hashed with SHA-256. Proof
siblings are ordered by raw bytes before they are concatenated. Differences
from the Rust example: checked `u128`
amounts, and `fail` instead of `Result`. Claimed indexes are stored as `u32`
keys. The test host encodes a non-StrKey address as the contract id
SHA-256(address).
"""

from pysoroban import (
    Address,
    Bytes,
    BytesN,
    Symbol,
    Vec,
    contract,
    crypto,
    env,
    error,
    fail,
    i32,
    public,
    storage,
    struct,
    to_xdr,
    u32,
    u128,
)


@error
class MerkleError:
    ALREADY_CLAIMED = 1
    INVALID_PROOF = 2


@struct
class Receiver:
    index: u32
    address: Address
    amount: u128


@contract
class MerkleDistribution:
    @public
    def __constructor(
        self,
        root_hash: BytesN[32],
        token: Address,
        funding_amount: u128,
        funding_source: Address,
    ) -> None:
        funding_source.require_auth()
        storage.instance.set(Symbol("root"), root_hash)
        storage.instance.set(Symbol("token"), token)
        self_address: Address = env.current_contract_address()
        token.call_void(Symbol("transfer"), funding_source, self_address, funding_amount)

    @public
    def leaf_hash(self, index: u32, receiver: Address, amount: u128) -> Bytes:
        return crypto.sha256(to_xdr(Receiver(index, receiver, amount)))

    @public
    def claim(
        self,
        index: u32,
        receiver: Address,
        amount: u128,
        proof: Vec[Bytes],
    ) -> None:
        receiver.require_auth()
        if storage.instance.has(index):
            fail(MerkleError.ALREADY_CLAIMED)
        current: Bytes = crypto.sha256(to_xdr(Receiver(index, receiver, amount)))
        count: i32 = len(proof)
        step: i32 = 0
        sibling: Bytes = Bytes(b"")
        left: Bytes = Bytes(b"")
        right: Bytes = Bytes(b"")
        combined: Bytes = Bytes(b"")
        for step in range(count):
            sibling = proof[step]
            if current < sibling:
                left = current
                right = sibling
            else:
                left = sibling
                right = current
            combined = left
            combined.append(right)
            current = crypto.sha256(combined)
        root: BytesN[32] = storage.instance.get(Symbol("root"), BytesN[32])
        digest: BytesN[32] = BytesN[32](current)
        if digest != root:
            fail(MerkleError.INVALID_PROOF)
        token: Address = storage.instance.get(Symbol("token"), Address)
        contract_address: Address = env.current_contract_address()
        token.call_void(Symbol("transfer"), contract_address, receiver, amount)
        storage.instance.set(index, True)
