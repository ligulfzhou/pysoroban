from pysoroban import Address, Bytes, Symbol, contract, deploy, public, storage, u32


@contract
class UpgradeableContract:
    @public
    def initialize(self, admin: Address) -> None:
        storage.instance.set(Symbol("Admin"), admin)

    @public
    def version(self) -> u32:
        return u32(1)

    @public
    def upgrade(self, new_wasm_hash: Bytes) -> None:
        admin: Address = storage.instance.get_address(Symbol("Admin"))
        admin.require_auth()
        deploy.upgrade(new_wasm_hash)
