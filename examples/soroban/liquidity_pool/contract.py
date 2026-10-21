from pysoroban import (
    Address,
    Symbol,
    boolean,
    contract,
    env,
    error,
    fail,
    public,
    storage,
    struct,
    u128,
)


@error
class PoolError:
    TOKEN_ORDER = 1
    AMOUNT_B = 2
    AMOUNT_A = 3
    AMOUNTS = 4
    NOT_ENOUGH = 5
    IN_AMOUNT = 6
    INVARIANT = 7
    RESERVES = 8
    SHARES = 9
    MINIMUM = 10


@struct
class Reserves:
    a: u128
    b: u128


@struct
class Withdrawal:
    a: u128
    b: u128


@contract
class LiquidityPool:
    """Constant-product pool that moves tokens, with a 0.3% swap fee.

    Amounts are checked u128 values. Upstream returns tuples and orders token
    addresses; tuples are structs here, and only equal addresses are rejected
    because addresses have no ordering. The initial share supply is an integer
    square root. The invariant split avoids negative deltas, which u128 cannot
    represent. Share balances are persistent entries keyed by the holder.
    """

    @public
    def initialize(self, token_a: Address, token_b: Address) -> None:
        if token_a == token_b:
            fail(PoolError.TOKEN_ORDER)
        storage.instance.set(Symbol("token_a"), token_a)
        storage.instance.set(Symbol("token_b"), token_b)
        storage.instance.set(Symbol("shares"), u128(0))
        storage.instance.set(Symbol("reserve_a"), u128(0))
        storage.instance.set(Symbol("reserve_b"), u128(0))

    @public
    def balance_shares(self, user: Address) -> u128:
        if storage.persistent.has(user):
            return storage.persistent.get(user, u128)
        return u128(0)

    @public
    def deposit(
        self,
        to: Address,
        desired_a: u128,
        min_a: u128,
        desired_b: u128,
        min_b: u128,
    ) -> None:
        to.require_auth()
        reserve_a: u128 = storage.instance.get_u128(Symbol("reserve_a"))
        reserve_b: u128 = storage.instance.get_u128(Symbol("reserve_b"))
        amount_a: u128 = desired_a
        amount_b: u128 = desired_b
        if reserve_a == u128(0):
            if reserve_b != u128(0):
                fail(PoolError.AMOUNT_A)
        else:
            proposed_b: u128 = desired_a * reserve_b // reserve_a
            if proposed_b <= desired_b:
                if proposed_b < min_b:
                    fail(PoolError.AMOUNT_B)
                amount_b = proposed_b
            else:
                proposed_a: u128 = desired_b * reserve_a // reserve_b
                if proposed_a > desired_a:
                    fail(PoolError.AMOUNT_A)
                if proposed_a < min_a:
                    fail(PoolError.AMOUNT_A)
                amount_a = proposed_a
        if amount_a == u128(0):
            fail(PoolError.AMOUNTS)
        if amount_b == u128(0):
            fail(PoolError.AMOUNTS)
        token_a: Address = storage.instance.get_address(Symbol("token_a"))
        token_b: Address = storage.instance.get_address(Symbol("token_b"))
        me: Address = env.current_contract_address()
        token_a.call_void(Symbol("transfer"), to, me, amount_a)
        token_b.call_void(Symbol("transfer"), to, me, amount_b)
        balance_a: u128 = token_a.call_u128(Symbol("balance"), me)
        balance_b: u128 = token_b.call_u128(Symbol("balance"), me)
        total: u128 = storage.instance.get_u128(Symbol("shares"))
        new_total: u128 = u128(0)
        product: u128 = u128(0)
        guess: u128 = u128(1)
        if reserve_a > u128(0):
            shares_a: u128 = balance_a * total // reserve_a
            shares_b: u128 = balance_b * total // reserve_b
            new_total = shares_a
            if shares_b < shares_a:
                new_total = shares_b
        else:
            product = balance_a * balance_b
            guess = product
            for _step in range(128):
                guess = (guess + product // guess) // u128(2)
            if guess * guess > product:
                guess = guess - u128(1)
            new_total = guess
        current: u128 = u128(0)
        if storage.persistent.has(to):
            current = storage.persistent.get(to, u128)
        storage.persistent.set(to, current + new_total - total)
        storage.instance.set(Symbol("shares"), new_total)
        storage.instance.set(Symbol("reserve_a"), balance_a)
        storage.instance.set(Symbol("reserve_b"), balance_b)

    @public
    def swap(self, to: Address, buy_a: boolean, out: u128, in_max: u128) -> None:
        to.require_auth()
        reserve_a: u128 = storage.instance.get_u128(Symbol("reserve_a"))
        reserve_b: u128 = storage.instance.get_u128(Symbol("reserve_b"))
        reserve_sell: u128 = reserve_a
        reserve_buy: u128 = reserve_b
        if buy_a:
            reserve_sell = reserve_b
            reserve_buy = reserve_a
        if reserve_buy < out:
            fail(PoolError.NOT_ENOUGH)
        sell_amount: u128 = reserve_sell * out * u128(1000) // ((reserve_buy - out) * u128(997)) + u128(1)
        if sell_amount > in_max:
            fail(PoolError.IN_AMOUNT)
        token_a: Address = storage.instance.get_address(Symbol("token_a"))
        token_b: Address = storage.instance.get_address(Symbol("token_b"))
        sell_token: Address = token_a
        if buy_a:
            sell_token = token_b
        me: Address = env.current_contract_address()
        sell_token.call_void(Symbol("transfer"), to, me, sell_amount)
        balance_a: u128 = token_a.call_u128(Symbol("balance"), me)
        balance_b: u128 = token_b.call_u128(Symbol("balance"), me)
        out_a: u128 = u128(0)
        out_b: u128 = u128(0)
        if buy_a:
            out_a = out
        else:
            out_b = out
        factor_a: u128 = u128(1000) * reserve_a
        factor_b: u128 = u128(1000) * reserve_b
        if balance_a >= reserve_a + out_a:
            factor_a = factor_a + u128(997) * (balance_a - reserve_a - out_a)
        else:
            factor_a = factor_a - u128(1000) * (reserve_a + out_a - balance_a)
        if balance_b >= reserve_b + out_b:
            factor_b = factor_b + u128(997) * (balance_b - reserve_b - out_b)
        else:
            factor_b = factor_b - u128(1000) * (reserve_b + out_b - balance_b)
        if factor_a * factor_b < u128(1000) * reserve_a * (u128(1000) * reserve_b):
            fail(PoolError.INVARIANT)
        if buy_a:
            token_a.call_void(Symbol("transfer"), me, to, out_a)
        else:
            token_b.call_void(Symbol("transfer"), me, to, out_b)
        new_reserve_a: u128 = balance_a - out_a
        new_reserve_b: u128 = balance_b - out_b
        if new_reserve_a == u128(0):
            fail(PoolError.RESERVES)
        if new_reserve_b == u128(0):
            fail(PoolError.RESERVES)
        storage.instance.set(Symbol("reserve_a"), new_reserve_a)
        storage.instance.set(Symbol("reserve_b"), new_reserve_b)

    @public
    def withdraw(self, to: Address, share_amount: u128, min_a: u128, min_b: u128) -> Withdrawal:
        to.require_auth()
        current: u128 = u128(0)
        if storage.persistent.has(to):
            current = storage.persistent.get(to, u128)
        if current < share_amount:
            fail(PoolError.SHARES)
        token_a: Address = storage.instance.get_address(Symbol("token_a"))
        token_b: Address = storage.instance.get_address(Symbol("token_b"))
        me: Address = env.current_contract_address()
        balance_a: u128 = token_a.call_u128(Symbol("balance"), me)
        balance_b: u128 = token_b.call_u128(Symbol("balance"), me)
        total: u128 = storage.instance.get_u128(Symbol("shares"))
        out_a: u128 = balance_a * share_amount // total
        out_b: u128 = balance_b * share_amount // total
        if out_a < min_a:
            fail(PoolError.MINIMUM)
        if out_b < min_b:
            fail(PoolError.MINIMUM)
        storage.persistent.set(to, current - share_amount)
        storage.instance.set(Symbol("shares"), total - share_amount)
        token_a.call_void(Symbol("transfer"), me, to, out_a)
        token_b.call_void(Symbol("transfer"), me, to, out_b)
        storage.instance.set(Symbol("reserve_a"), balance_a - out_a)
        storage.instance.set(Symbol("reserve_b"), balance_b - out_b)
        return Withdrawal(out_a, out_b)

    @public
    def get_rsrvs(self) -> Reserves:
        return Reserves(
            storage.instance.get_u128(Symbol("reserve_a")),
            storage.instance.get_u128(Symbol("reserve_b")),
        )
