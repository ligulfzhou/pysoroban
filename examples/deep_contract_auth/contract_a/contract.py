from pysoroban import Address, Symbol, auth, contract, env, public


@contract
class ContractA:
    """Pre-authorize contract C, then call contract B.

    The entry is one Contract invocation with one address argument and no
    further sub-invocations. The direct call to B is authorized because A
    calls it.
    """

    @public
    def call_b(self, contract_b: Address, contract_c: Address) -> None:
        me: Address = env.current_contract_address()
        auth.as_current_contract(contract_c, Symbol("authorized_fn_c"), me)
        contract_b.call_void(Symbol("authorized_fn_b"), me, contract_c)
