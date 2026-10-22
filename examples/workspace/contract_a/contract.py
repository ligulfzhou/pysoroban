from pysoroban import contract, public, u32


@contract
class ContractA:
    """workspace/contract_a.

    A Cargo workspace is a Rust build layout, not a contract feature. This is
    the same add function the workspace builds behind a Rust trait.
    """

    @public
    def add(self, x: u32, y: u32) -> u32:
        return x + y
