"""Relay a notification to a contract function that returns None."""

from pysoroban import Address, Symbol, contract, public, u64


@contract
class NotificationRelay:
    @public
    def notify(self, target: Address, recipient: Address, amount: u64) -> None:
        target.call_void(Symbol("record"), recipient, amount)
