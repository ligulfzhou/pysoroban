from pysoroban import (
    Address,
    BytesN,
    Symbol,
    Val,
    Vec,
    contract,
    crypto,
    i32,
    error,
    fail,
    public,
    storage,
    struct,
    union,
)


@error
class Error:
    UNKNOWN_SIGNER = 1


@struct
class Signature:
    public_key: BytesN[32]
    signature: BytesN[64]


@union
class DataKey:
    Signer: BytesN[32]


@struct
class ContractContext:
    contract: Address
    fn_name: Symbol
    args: Vec[Val]


@union
class Context:
    Contract: ContractContext


@contract
class MultisigAccount:
    """Any one configured ed25519 key may sign.

    The signature context is not consulted. initialize replaces __constructor.
    """

    @public
    def initialize(self, signers: Vec[BytesN[32]]) -> None:
        signer: BytesN[32] = signers[0]
        index: i32 = 0
        for index in range(len(signers)):
            signer = signers[index]
            storage.instance.set(DataKey.Signer(signer), True)

    @public
    def __check_auth(
        self,
        signature_payload: BytesN[32],
        signature: Signature,
        auth_context: Vec[Context],
    ) -> None:
        if storage.instance.has(DataKey.Signer(signature.public_key)) == False:
            fail(Error.UNKNOWN_SIGNER)
        crypto.ed25519_verify(signature.public_key, signature_payload, signature.signature)
