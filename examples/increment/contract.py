from pysoroban import Symbol, contract, public, storage, u32


@contract
class IncrementContract:
    """Instance counter from stellar/soroban-examples increment.

    Formatted log! lines are omitted: log() accepts a String and cannot
    interpolate a number. extend_ttl matches the upstream thresholds.
    """

    @public
    def increment(self) -> u32:
        count: u32 = u32(0)
        if storage.instance.has(Symbol("COUNTER")):
            count = storage.instance.get_u32(Symbol("COUNTER"))
        count = count + u32(1)
        storage.instance.set(Symbol("COUNTER"), count)
        storage.instance.extend_ttl(u32(50), u32(100))
        return count
