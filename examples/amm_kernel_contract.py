"""Constant-product accounting kernel used to drive PySoroban development.

This testnet reference intentionally does not transfer tokens. It exercises the
math, authorization, storage, event, and minimum-output semantics that a full
AMM will need while token integration and the liquidity lifecycle are built.
"""

from pysoroban import Address, Symbol, Topic, contract, event, events, public, storage, u128


@event
class PoolInitialized:
    provider: Topic[Address]
    shares: u128


@event
class Swapped:
    trader: Topic[Address]
    amount_out: u128


@contract
class ConstantProductKernel:
    @public
    def initialize(self, provider: Address, reserve_a: u128, reserve_b: u128) -> u128:
        provider.require_auth()
        if storage.instance.has(Symbol("reserve_a")):
            return u128(0)
        if reserve_a == u128(0) or reserve_b == u128(0):
            return u128(0)

        shares: u128 = reserve_a
        if reserve_b < reserve_a:
            shares = reserve_b
        storage.instance.set(Symbol("reserve_a"), reserve_a)
        storage.instance.set(Symbol("reserve_b"), reserve_b)
        storage.instance.set(Symbol("total_shares"), shares)
        events.publish(PoolInitialized(provider, shares))
        return shares

    @public
    def quote(self, amount_in: u128, reserve_in: u128, reserve_out: u128) -> u128:
        if amount_in == u128(0) or reserve_in == u128(0) or reserve_out == u128(0):
            return u128(0)
        amount_in_with_fee: u128 = u128.mul_div_floor(amount_in, u128(997), u128(1))
        reserve_in_scaled: u128 = u128.mul_div_floor(reserve_in, u128(1000), u128(1))
        denominator: u128 = reserve_in_scaled + amount_in_with_fee
        return u128.mul_div_floor(amount_in_with_fee, reserve_out, denominator)

    @public
    def swap_a_for_b(self, trader: Address, amount_in: u128, minimum_out: u128) -> u128:
        trader.require_auth()
        if not storage.instance.has(Symbol("reserve_a")):
            return u128(0)
        if amount_in == u128(0):
            return u128(0)

        reserve_a: u128 = storage.instance.get_u128(Symbol("reserve_a"))
        reserve_b: u128 = storage.instance.get_u128(Symbol("reserve_b"))
        amount_in_with_fee: u128 = u128.mul_div_floor(amount_in, u128(997), u128(1))
        reserve_a_scaled: u128 = u128.mul_div_floor(reserve_a, u128(1000), u128(1))
        denominator: u128 = reserve_a_scaled + amount_in_with_fee
        amount_out: u128 = u128.mul_div_floor(amount_in_with_fee, reserve_b, denominator)
        if amount_out == u128(0) or amount_out < minimum_out or amount_out >= reserve_b:
            return u128(0)

        storage.instance.set(Symbol("reserve_a"), reserve_a + amount_in)
        storage.instance.set(Symbol("reserve_b"), reserve_b - amount_out)
        events.publish(Swapped(trader, amount_out))
        return amount_out

    @public
    def reserve_a(self) -> u128:
        if not storage.instance.has(Symbol("reserve_a")):
            return u128(0)
        return storage.instance.get_u128(Symbol("reserve_a"))

    @public
    def reserve_b(self) -> u128:
        if not storage.instance.has(Symbol("reserve_b")):
            return u128(0)
        return storage.instance.get_u128(Symbol("reserve_b"))

    @public
    def total_shares(self) -> u128:
        if not storage.instance.has(Symbol("total_shares")):
            return u128(0)
        return storage.instance.get_u128(Symbol("total_shares"))
