from pysoroban import Symbol, contract, events, public, storage, u32


@contract
class IncrementContract:
    """Publishes the new count.

    Upstream uses two static topics, COUNTER and increment. PySoroban events
    have one symbol topic, so this publishes Symbol("increment") and the count.
    """

    @public
    def increment(self) -> u32:
        count: u32 = u32(0)
        if storage.instance.has(Symbol("COUNTER")):
            count = storage.instance.get_u32(Symbol("COUNTER"))
        count = count + u32(1)
        storage.instance.set(Symbol("COUNTER"), count)
        events.publish(Symbol("increment"), count)
        return count
