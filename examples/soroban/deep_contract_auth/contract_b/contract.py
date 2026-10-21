from pysoroban import Address, Symbol, contract, public


@contract
class ContractB:
    @public
    def authorized_fn_b(self, authorizer: Address, contract_c: Address) -> None:
        authorizer.require_auth()
        contract_c.call_void(Symbol("authorized_fn_c"), authorizer)
