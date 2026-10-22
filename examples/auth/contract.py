from pysoroban import Address, contract, public, storage, u32


@contract
class IncrementContract:
    """Per-address counter.

    Upstream stores DataKey::Counter(user), a data-carrying enum. Those enums
    are not available, so the persistent key is the address itself.
    """

    @public
    def increment(self, user: Address, value: u32) -> u32:
        user.require_auth_for(user, value)
        count: u32 = u32(0)
        if storage.persistent.has(user):
            count = storage.persistent.get(user, u32)
        count = count + value
        storage.persistent.set(user, count)
        return count
