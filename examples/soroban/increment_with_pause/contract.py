from pysoroban import Address, Symbol, contract, error, fail, public, storage, u32


@error
class Error:
    PAUSED = 1


@contract
class IncrementContract:
    """Counter gated by a pause contract.

    Upstream uses __constructor. Call initialize before increment. Result is
    expressed with fail because the language has no Result type.
    """

    @public
    def initialize(self, pause: Address) -> None:
        storage.instance.set(Symbol("PAUSE"), pause)

    @public
    def increment(self) -> u32:
        pause: Address = storage.instance.get_address(Symbol("PAUSE"))
        if pause.call_bool(Symbol("paused")):
            fail(Error.PAUSED)
        count: u32 = u32(0)
        if storage.instance.has(Symbol("COUNTER")):
            count = storage.instance.get_u32(Symbol("COUNTER"))
        count = count + u32(1)
        storage.instance.set(Symbol("COUNTER"), count)
        storage.instance.extend_ttl(u32(50), u32(100))
        return count
