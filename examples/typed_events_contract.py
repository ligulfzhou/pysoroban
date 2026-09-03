from pysoroban import Address, Bytes, String, Symbol, Topic, contract, event, events, i64, public, storage, u32, u64


@event
class Updated:
    """A total changed after its owner authorized an update."""

    owner: Topic[Address]
    value: u64


@contract
class TypedEvents:
    @public
    def record(self, owner: Address, amount: u64) -> u64:
        """Authorize, persist, and announce a new total."""
        owner.require_auth()
        key: Symbol = Symbol("total")
        current: u64 = u64(0)
        if storage.instance.has(key):
            current = storage.instance.get_u64(key)
        updated: u64 = current + amount
        storage.instance.set(key, updated)
        events.publish(Updated(owner, updated))
        return updated

    @public
    def offset(self, value: i64) -> i64:
        return value + i64(-7)

    @public
    def generation(self) -> u32:
        return u32(2)

    @public
    def label(self) -> String:
        return String("PySoroban")

    @public
    def fingerprint(self) -> Bytes:
        return Bytes(b"py-soroban")
