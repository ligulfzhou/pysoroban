from pysoroban import Address, Bytes, Symbol, contract, deploy, public, storage, u32


@contract
class Deployer:
    """Factory that deploys a Wasm hash with constructor arguments.

    deploy.with_constructor passes the arguments as a host vector. The test
    host runs the child installed with ``register_wasm`` for that hash.
    """

    @public
    def __constructor(self, admin: Address) -> None:
        storage.instance.set(Symbol("admin"), admin)

    @public
    def deploy(self, wasm_hash: Bytes, salt: Bytes, value: u32) -> Address:
        admin: Address = storage.instance.get_address(Symbol("admin"))
        admin.require_auth()
        return deploy.with_constructor(wasm_hash, salt, value)
