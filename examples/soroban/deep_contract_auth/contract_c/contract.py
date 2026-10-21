from pysoroban import Address, contract, public


@contract
class ContractC:
    @public
    def authorized_fn_c(self, authorizer: Address) -> None:
        authorizer.require_auth()
