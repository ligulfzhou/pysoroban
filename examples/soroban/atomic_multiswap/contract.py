from pysoroban import Address, Symbol, Vec, boolean, contract, public, struct, u128


@struct
class SwapSpec:
    address: Address
    amount: u128
    min_recv: u128


@contract
class AtomicMultiSwapContract:
    """Match two lists of swap specs and invoke the atomic swap contract.

    Upstream uses try_swap so one failed pair does not abort the batch. There
    is no try_call, so a trapped swap aborts every match in this invocation.
    break is not available, so a matched counterparty is marked and skipped.
    """

    @public
    def multi_swap(
        self,
        swap_contract: Address,
        token_a: Address,
        token_b: Address,
        swaps_a: Vec[SwapSpec],
        swaps_b: Vec[SwapSpec],
    ) -> None:
        if len(swaps_a) == 0:
            return
        if len(swaps_b) == 0:
            return
        acc_a: SwapSpec = swaps_a[0]
        acc_b: SwapSpec = swaps_b[0]
        used: Vec[boolean] = Vec()
        matched: boolean = False
        for index_b in range(len(swaps_b)):
            used.push(False)
        for index_a in range(len(swaps_a)):
            acc_a = swaps_a[index_a]
            matched = False
            for index_b in range(len(swaps_b)):
                if matched == False:
                    if used[index_b] == False:
                        acc_b = swaps_b[index_b]
                        if acc_a.amount >= acc_b.min_recv:
                            if acc_a.min_recv <= acc_b.amount:
                                swap_contract.call_void(
                                    Symbol("swap"),
                                    acc_a.address,
                                    acc_b.address,
                                    token_a,
                                    token_b,
                                    acc_a.amount,
                                    acc_a.min_recv,
                                    acc_b.amount,
                                    acc_b.min_recv,
                                )
                                used.set(index_b, True)
                                matched = True
