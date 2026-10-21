from pysoroban import (
    Address,
    BytesN,
    Symbol,
    Val,
    Vec,
    contract,
    crypto,
    error,
    fail,
    public,
    storage,
    struct,
    union,
)


@error
class AccountError:
    ALREADY_SET = 1


@union
class DataKey:
    Owner: None


@struct
class ContractContext:
    contract: Address
    fn_name: Symbol
    args: Vec[Val]


@union
class Context:
    Contract: ContractContext


@contract
class SimpleAccount:
    """Single ed25519 owner.

    ``__constructor`` runs once. __check_auth does not read the
    auth context. The test host invokes __check_auth only after
    authorize_account.
    """

    @public
    def __constructor(self, public_key: BytesN[32]) -> None:
        if storage.instance.has(DataKey.Owner()):
            fail(AccountError.ALREADY_SET)
        storage.instance.set(DataKey.Owner(), public_key)

    @public
    def __check_auth(
        self,
        signature_payload: BytesN[32],
        signature: BytesN[64],
        auth_context: Vec[Context],
    ) -> None:
        owner: BytesN[32] = storage.instance.get(DataKey.Owner(), BytesN[32])
        crypto.ed25519_verify(owner, signature_payload, signature)
