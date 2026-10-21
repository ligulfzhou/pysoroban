from pysoroban import Symbol, contract, error, fail, public, storage, u32


@error
class Error:
    LIMIT_REACHED = 1


@contract
class IncrementContract:
    @public
    def increment(self) -> u32:
        count: u32 = u32(0)
        if storage.instance.has(Symbol("COUNTER")):
            count = storage.instance.get_u32(Symbol("COUNTER"))
        count = count + u32(1)
        if count <= u32(5):
            storage.instance.set(Symbol("COUNTER"), count)
            return count
        fail(Error.LIMIT_REACHED)
