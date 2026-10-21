from pysoroban import Address, Symbol, Vec, contract, public, storage, u32


@contract
class StorageTiers:
    """Instance, persistent, and temporary storage with collection updates."""

    @public
    def remember(self, admin: Address, value: u32) -> u32:
        storage.instance.set(Symbol("admin"), admin)
        storage.persistent.set(admin, value)
        values: Vec[u32] = Vec()
        values.push(value)
        storage.temporary.set(Symbol("recent"), values)
        storage.persistent.extend_ttl(admin, u32(16), u32(64))
        storage.instance.extend_ttl(u32(16), u32(64))
        return value

    @public
    def admin(self) -> Address:
        return storage.instance.get_address(Symbol("admin"))

    @public
    def balance(self, admin: Address) -> u32:
        if storage.persistent.has(admin):
            return storage.persistent.get(admin, u32)
        return u32(0)

    @public
    def recent(self) -> u32:
        values: Vec[u32] = storage.temporary.get(Symbol("recent"), Vec[u32])
        return values[0]

    @public
    def clear(self, admin: Address) -> None:
        if storage.persistent.has(admin):
            storage.persistent.remove(admin)
        if storage.temporary.has(Symbol("recent")):
            storage.temporary.remove(Symbol("recent"))
