from pysoroban import Symbol, boolean, contract, public, storage


@contract
class Pause:
    @public
    def paused(self) -> boolean:
        if storage.instance.has(Symbol("PAUSED")):
            return storage.instance.get_bool(Symbol("PAUSED"))
        return False

    @public
    def set(self, paused: boolean) -> None:
        storage.instance.set(Symbol("PAUSED"), paused)
