from pysoroban import Symbol, contract, public, storage, struct, u32


@struct
class State:
    count: u32
    last_incr: u32


@contract
class IncrementContract:
    @public
    def increment(self, incr: u32) -> u32:
        state: State = State(u32(0), u32(0))
        if storage.instance.has(Symbol("STATE")):
            state = storage.instance.get(Symbol("STATE"), State)
        updated: State = State(state.count + incr, incr)
        storage.instance.set(Symbol("STATE"), updated)
        return updated.count

    @public
    def get_state(self) -> State:
        if storage.instance.has(Symbol("STATE")):
            return storage.instance.get(Symbol("STATE"), State)
        return State(u32(0), u32(0))
