from pysoroban import Address, Bytes, Symbol, contract, deploy, public, storage, u32


@contract
class UpgradeableContract:
    """Version 2 of the upgradeable contract.

    Upstream does not run the constructor on upgrade. handle_upgrade copies
    Admin into NewAdmin when that key is missing. There is no migration host
    function; the caller invokes handle_upgrade after deploy.upgrade.
    """

    @public
    def __constructor(self, admin: Address) -> None:
        storage.instance.set(Symbol("Admin"), admin)
        storage.instance.set(Symbol("NewAdmin"), admin)

    @public
    def handle_upgrade(self) -> None:
        admin: Address = storage.instance.get_address(Symbol("Admin"))
        admin.require_auth()
        if not storage.instance.has(Symbol("NewAdmin")):
            storage.instance.set(Symbol("NewAdmin"), admin)

    @public
    def version(self) -> u32:
        return u32(2)

    @public
    def new_v2_fn(self) -> u32:
        return u32(1010101)

    @public
    def upgrade(self, new_wasm_hash: Bytes) -> None:
        admin: Address = storage.instance.get_address(Symbol("NewAdmin"))
        admin.require_auth()
        deploy.upgrade(new_wasm_hash)
