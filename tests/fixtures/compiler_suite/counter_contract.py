from pysoroban import Address, contract, i32, public, storage


@contract
class Counter:
    @public
    def increment(self, user: Address, amount: i32) -> i32:
        user.require_auth()
        current: i32 = 0
        if storage.instance.has(user):
            current = storage.instance.get_i32(user)
        updated: i32 = current + amount
        storage.instance.set(user, updated)
        return updated

    @public
    def value(self, user: Address) -> i32:
        if storage.instance.has(user):
            return storage.instance.get_i32(user)
        return 0
