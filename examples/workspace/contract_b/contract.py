from pysoroban import Address, Symbol, contract, public, u32


@contract
class ContractB:
    @public
    def add_with(self, contract: Address, x: u32, y: u32) -> u32:
        return contract.call_u32(Symbol("add"), x, y)
