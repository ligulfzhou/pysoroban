from pysoroban import Address, Symbol, contract, env, error, fail, public, u128


@error
class SwapError:
    NOT_ENOUGH_B = 1
    NOT_ENOUGH_A = 2


@contract
class AtomicSwapContract:
    """Atomic two-party token swap.

    Amounts are checked u128 values. The upstream token interface uses i128.
    A failed price check traps with fail, which rolls the call back. There is
    no try_swap, so a caller cannot ignore that failure.
    """

    @public
    def swap(
        self,
        a: Address,
        b: Address,
        token_a: Address,
        token_b: Address,
        amount_a: u128,
        min_b_for_a: u128,
        amount_b: u128,
        min_a_for_b: u128,
    ) -> None:
        if amount_b < min_b_for_a:
            fail(SwapError.NOT_ENOUGH_B)
        if amount_a < min_a_for_b:
            fail(SwapError.NOT_ENOUGH_A)
        a.require_auth_for(token_a, token_b, amount_a, min_b_for_a)
        b.require_auth_for(token_b, token_a, amount_b, min_a_for_b)
        self_address: Address = env.current_contract_address()
        token_a.call_void(Symbol("transfer"), a, self_address, amount_a)
        token_a.call_void(Symbol("transfer"), self_address, b, min_a_for_b)
        refund_a: u128 = amount_a - min_a_for_b
        token_a.call_void(Symbol("transfer"), self_address, a, refund_a)
        token_b.call_void(Symbol("transfer"), b, self_address, amount_b)
        token_b.call_void(Symbol("transfer"), self_address, a, min_b_for_a)
        refund_b: u128 = amount_b - min_b_for_a
        token_b.call_void(Symbol("transfer"), self_address, b, refund_b)
