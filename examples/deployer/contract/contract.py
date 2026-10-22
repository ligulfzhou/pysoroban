from pysoroban import Symbol, contract, public, storage, u32


@contract
class Contract:
    """Child contract deployed by the factory.

    Upstream sets the value in __constructor. The test host records constructor
    arguments and does not invoke this contract, so tests call initialize.
    """

    @public
    def initialize(self, value: u32) -> None:
        storage.instance.set(Symbol("value"), value)

    @public
    def value(self) -> u32:
        return storage.instance.get_u32(Symbol("value"))
