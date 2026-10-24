from pysoroban import Symbol, contract, public, storage, u32


@contract
class Contract:
    """Child contract deployed by the factory.

    Upstream sets the value in ``__constructor``. Register this compilation
    with ``register_wasm`` and the factory's ``deploy.with_constructor`` runs
    that constructor.
    """

    @public
    def __constructor(self, value: u32) -> None:
        storage.instance.set(Symbol("value"), value)

    @public
    def value(self) -> u32:
        return storage.instance.get_u32(Symbol("value"))
