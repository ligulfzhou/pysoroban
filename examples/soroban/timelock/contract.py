from pysoroban import (
    Address,
    Symbol,
    Vec,
    boolean,
    contract,
    enum,
    env,
    error,
    fail,
    ledger,
    public,
    storage,
    struct,
    u128,
    u64,
)


@error
class TimelockError:
    TOO_MANY_CLAIMANTS = 1
    ALREADY_INITIALIZED = 2
    TIME_NOT_FULFILLED = 3
    CLAIMANT_NOT_ALLOWED = 4


@enum
class TimeBoundKind:
    BEFORE = 0
    AFTER = 1


@struct
class TimeBound:
    kind: TimeBoundKind
    timestamp: u64


@struct
class ClaimableBalance:
    token: Address
    amount: u128
    claimants: Vec[Address]
    time_bound: TimeBound


@contract
class ClaimableBalanceContract:
    """One claimable balance with a before/after timestamp.

    Amounts are u128. Upstream panics are fail cases. Vec membership is a loop
    because there is no contains method.
    """

    @public
    def deposit(
        self,
        from_account: Address,
        token: Address,
        amount: u128,
        claimants: Vec[Address],
        time_bound: TimeBound,
    ) -> None:
        if len(claimants) > 10:
            fail(TimelockError.TOO_MANY_CLAIMANTS)
        if storage.instance.has(Symbol("Init")):
            fail(TimelockError.ALREADY_INITIALIZED)
        from_account.require_auth()
        token.call_void(
            Symbol("transfer"),
            from_account,
            env.current_contract_address(),
            amount,
        )
        balance: ClaimableBalance = ClaimableBalance(token, amount, claimants, time_bound)
        storage.instance.set(Symbol("Balance"), balance)
        storage.instance.set(Symbol("Init"), True)

    @public
    def claim(self, claimant: Address) -> None:
        claimant.require_auth()
        balance: ClaimableBalance = storage.instance.get(Symbol("Balance"), ClaimableBalance)
        bound: TimeBound = balance.time_bound
        allowed_time: boolean = False
        if bound.kind == TimeBoundKind.BEFORE:
            allowed_time = ledger.timestamp() <= bound.timestamp
        else:
            allowed_time = ledger.timestamp() >= bound.timestamp
        if allowed_time == False:
            fail(TimelockError.TIME_NOT_FULFILLED)
        holders: Vec[Address] = balance.claimants
        found: boolean = False
        for index in range(len(holders)):
            if holders[index] == claimant:
                found = True
        if found == False:
            fail(TimelockError.CLAIMANT_NOT_ALLOWED)
        token: Address = balance.token
        token.call_void(
            Symbol("transfer"),
            env.current_contract_address(),
            claimant,
            balance.amount,
        )
        storage.instance.remove(Symbol("Balance"))
