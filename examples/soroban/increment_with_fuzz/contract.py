from pysoroban import Symbol, contract, public, storage, u32


@contract
class IncrementContract:
    """The increment contract used by increment_with_fuzz.

    The cargo-fuzz harness is a Rust test target, not a contract, so it is not
    ported. The contract behavior matches increment.
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
