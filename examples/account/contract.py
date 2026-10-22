from pysoroban import (
    Address,
    BytesN,
    Map,
    Symbol,
    Val,
    Vec,
    boolean,
    contract,
    crypto,
    env,
    error,
    fail,
    i128,
    i32,
    public,
    storage,
    struct,
    union,
)


@error
class AccError:
    NOT_ENOUGH_SIGNERS = 1
    NEGATIVE_AMOUNT = 2
    BAD_SIGNATURE_ORDER = 3
    UNKNOWN_SIGNER = 4


@struct
class AccSignature:
    public_key: BytesN[32]
    signature: BytesN[64]


@union
class DataKey:
    SignerCnt: None
    Signer: BytesN[32]
    SpendLimit: Address


@struct
class ContractContext:
    contract: Address
    fn_name: Symbol
    args: Vec[Val]


@union
class Context:
    """Contract invocations only.

    Create-contract host contexts are not represented. A context that is not
    Contract fails closed unless every signer signed.
    """

    Contract: ContractContext


@contract
class AccountContract:
    """Multisig account with a per-token spend limit.

    Signer count is i32 because len() is i32. Amounts are i128. The test host
    does not build Context values; authorize_account supplies them.
    ``__constructor`` installs the signers.
    """

    @public
    def __constructor(self, signers: Vec[BytesN[32]]) -> None:
        signer: BytesN[32] = signers[0]
        index: i32 = 0
        for index in range(len(signers)):
            signer = signers[index]
            storage.instance.set(DataKey.Signer(signer), True)
        storage.instance.set(DataKey.SignerCnt(), len(signers))

    @public
    def add_limit(self, token: Address, limit: i128) -> None:
        account: Address = env.current_contract_address()
        account.require_auth()
        storage.instance.set(DataKey.SpendLimit(token), limit)

    @public
    def __check_auth(
        self,
        signature_payload: BytesN[32],
        signatures: Vec[AccSignature],
        auth_context: Vec[Context],
    ) -> None:
        count: i32 = len(signatures)
        index: i32 = 0
        current: AccSignature = signatures[0]
        previous: AccSignature = signatures[0]
        for index in range(count):
            current = signatures[index]
            if index > 0:
                previous = signatures[index - 1]
                if previous.public_key >= current.public_key:
                    fail(AccError.BAD_SIGNATURE_ORDER)
            if storage.instance.has(DataKey.Signer(current.public_key)) == False:
                fail(AccError.UNKNOWN_SIGNER)
            crypto.ed25519_verify(current.public_key, signature_payload, current.signature)
        total: i32 = storage.instance.get(DataKey.SignerCnt(), i32)
        all_signed: boolean = total == count
        if all_signed:
            return
        nctx: i32 = len(auth_context)
        if nctx == 0:
            return
        context: Context = auth_context[0]
        info: ContractContext = context.unwrap_Contract()
        current_contract: Address = env.current_contract_address()
        spent_left: Map[Address, i128] = Map()
        name: Symbol = Symbol("transfer")
        token: Address = current_contract
        args: Vec[Val] = info.args
        spent: i128 = i128(0)
        limit: i128 = i128(0)
        tracked: boolean = False
        for index in range(nctx):
            context = auth_context[index]
            if context.is_Contract() == False:
                fail(AccError.NOT_ENOUGH_SIGNERS)
            info = context.unwrap_Contract()
            if info.contract == current_contract:
                fail(AccError.NOT_ENOUGH_SIGNERS)
            name = info.fn_name
            if name == Symbol("transfer"):
                tracked = True
            if name == Symbol("approve"):
                tracked = True
            if name == Symbol("burn"):
                tracked = True
            if tracked:
                token = info.contract
                if spent_left.has(token):
                    limit = spent_left[token]
                if storage.instance.has(DataKey.SpendLimit(token)):
                    if spent_left.has(token) == False:
                        limit = storage.instance.get(DataKey.SpendLimit(token), i128)
                    tracked = True
                if spent_left.has(token) == False:
                    if storage.instance.has(DataKey.SpendLimit(token)) == False:
                        tracked = False
                if tracked:
                    args = info.args
                    spent = i128.from_val(args[2])
                    if spent < i128(0):
                        fail(AccError.NEGATIVE_AMOUNT)
                    if spent > limit:
                        fail(AccError.NOT_ENOUGH_SIGNERS)
                    spent_left.set(token, limit - spent)
            tracked = False
