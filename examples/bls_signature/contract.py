from pysoroban import (
    Address,
    Bytes,
    BytesN,
    Symbol,
    Val,
    Vec,
    contract,
    crypto,
    env,
    error,
    fail,
    public,
    storage,
    struct,
    u32,
    union,
)


@error
class AccError:
    InvalidSignature = 1


@union
class DataKey:
    Owners: None
    Counter: None
    Dst: None


@struct
class ContractContext:
    contract: Address
    fn_name: Symbol
    args: Vec[Val]


@union
class Context:
    Contract: ContractContext


@contract
class IncrementContract:
    """BLS12-381 aggregate account.

    ``__constructor`` stores the aggregated key. The test host does not evaluate
    the pairing. Queue hash_to_g2 bytes and a pairing boolean with
    allow_host_result before authorize_account.
    """

    @public
    def __constructor(self, agg_pk: BytesN[96]) -> None:
        storage.persistent.set(DataKey.Owners(), agg_pk)
        storage.instance.set(
            DataKey.Dst(),
            Bytes(b"BLSSIG-V01-CS01-with-BLS12381G2_XMD:SHA-256_SSWU_RO_"),
        )
        storage.instance.set(DataKey.Counter(), u32(0))

    @public
    def increment(self) -> u32:
        account: Address = env.current_contract_address()
        account.require_auth()
        count: u32 = storage.instance.get(DataKey.Counter(), u32)
        count = count + u32(1)
        storage.instance.set(DataKey.Counter(), count)
        return count

    @public
    def __check_auth(
        self,
        signature_payload: BytesN[32],
        agg_sig: BytesN[192],
        auth_context: Vec[Context],
    ) -> None:
        agg_pk: BytesN[96] = storage.persistent.get(DataKey.Owners(), BytesN[96])
        dst: Bytes = storage.instance.get(DataKey.Dst(), Bytes)
        msg_g2: Bytes = crypto.bls12_381_hash_to_g2(signature_payload, dst)
        neg: BytesN[96] = BytesN[96](Bytes(b"\x17\xf1\xd3\xa7\x31\x97\xd7\x94\x26\x95\x63\x8c\x4f\xa9\xac\x0f\xc3\x68\x8c\x4f\x97\x74\xb9\x05\xa1\x4e\x3a\x3f\x17\x1b\xac\x58\x6c\x55\xe8\x3f\xf9\x7a\x1a\xef\xfb\x3a\xf0\x0a\xdb\x22\xc6\xbb\x11\x4d\x1d\x68\x55\xd5\x45\xa8\xaa\x7d\x76\xc8\xcf\x2e\x21\xf2\x67\x81\x6a\xef\x1d\xb5\x07\xc9\x66\x55\xb9\xd5\xca\xac\x42\x36\x4e\x6f\x38\xba\x0e\xcb\x75\x1b\xad\x54\xdc\xd6\xb9\x39\xc2\xca"))
        left: Vec[Bytes] = Vec()
        left.push(agg_pk)
        left.push(neg)
        right: Vec[Bytes] = Vec()
        right.push(msg_g2)
        right.push(agg_sig)
        accepted: bool = crypto.bls12_381_multi_pairing_check(left, right)
        if accepted == False:
            fail(AccError.InvalidSignature)
