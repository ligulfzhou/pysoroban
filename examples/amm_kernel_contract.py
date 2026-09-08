"""Constant-product accounting kernel used to drive PySoroban development.

This testnet reference intentionally does not transfer tokens. It exercises the
math, authorization, storage, event, and minimum-output semantics that a full
AMM will need while the remaining token and asset-safety primitives are built.
"""

from pysoroban import Address, Symbol, Topic, contract, event, events, public, storage, u64


@event
class PoolInitialized:
    provider: Topic[Address]
    shares: u64


@event
class Swapped:
    trader: Topic[Address]
    amount_out: u64


@contract
class ConstantProductKernel:
    @public
    def initialize(self, provider: Address, reserve_a: u64, reserve_b: u64) -> u64:
        provider.require_auth()
        if storage.instance.has(Symbol("reserve_a")):
            return u64(0)
        if reserve_a == u64(0) or reserve_b == u64(0):
            return u64(0)

        shares: u64 = reserve_a
        if reserve_b < reserve_a:
            shares = reserve_b
        storage.instance.set(Symbol("reserve_a"), reserve_a)
        storage.instance.set(Symbol("reserve_b"), reserve_b)
        storage.instance.set(Symbol("total_shares"), shares)
        events.publish(PoolInitialized(provider, shares))
        return shares

    @public
    def quote(self, amount_in: u64, reserve_in: u64, reserve_out: u64) -> u64:
        if amount_in == u64(0) or reserve_in == u64(0) or reserve_out == u64(0):
            return u64(0)
        amount_in_with_fee: u64 = amount_in * u64(997)
        numerator: u64 = amount_in_with_fee * reserve_out
        denominator: u64 = reserve_in * u64(1000) + amount_in_with_fee
        return numerator // denominator

    @public
    def swap_a_for_b(self, trader: Address, amount_in: u64, minimum_out: u64) -> u64:
        trader.require_auth()
        if not storage.instance.has(Symbol("reserve_a")):
            return u64(0)
        if amount_in == u64(0):
            return u64(0)

        reserve_a: u64 = storage.instance.get_u64(Symbol("reserve_a"))
        reserve_b: u64 = storage.instance.get_u64(Symbol("reserve_b"))
        amount_in_with_fee: u64 = amount_in * u64(997)
        numerator: u64 = amount_in_with_fee * reserve_b
        denominator: u64 = reserve_a * u64(1000) + amount_in_with_fee
        amount_out: u64 = numerator // denominator
        if amount_out == u64(0) or amount_out < minimum_out or amount_out >= reserve_b:
            return u64(0)

        storage.instance.set(Symbol("reserve_a"), reserve_a + amount_in)
        storage.instance.set(Symbol("reserve_b"), reserve_b - amount_out)
        events.publish(Swapped(trader, amount_out))
        return amount_out

    @public
    def reserve_a(self) -> u64:
        if not storage.instance.has(Symbol("reserve_a")):
            return u64(0)
        return storage.instance.get_u64(Symbol("reserve_a"))

    @public
    def reserve_b(self) -> u64:
        if not storage.instance.has(Symbol("reserve_b")):
            return u64(0)
        return storage.instance.get_u64(Symbol("reserve_b"))

    @public
    def total_shares(self) -> u64:
        if not storage.instance.has(Symbol("total_shares")):
            return u64(0)
        return storage.instance.get_u64(Symbol("total_shares"))
