from pysoroban import Symbol, contract, public, storage, u32


@contract
class TtlContract:
    @public
    def setup(self) -> None:
        storage.persistent.set(Symbol("MyKey"), u32(0))
        storage.instance.set(Symbol("MyKey"), u32(1))
        storage.temporary.set(Symbol("MyKey"), u32(2))

    @public
    def extend_persistent(self) -> None:
        storage.persistent.extend_ttl(Symbol("MyKey"), u32(1000), u32(5000))

    @public
    def extend_instance(self) -> None:
        storage.instance.extend_ttl(u32(2000), u32(10000))

    @public
    def extend_temporary(self) -> None:
        storage.temporary.extend_ttl(Symbol("MyKey"), u32(3000), u32(7000))
