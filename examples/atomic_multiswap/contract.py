from pysoroban import Address, Result, Symbol, Vec, boolean, contract, error, public, struct, u128, u32


@struct
class SwapSpec:
    address: Address
    amount: u128
    min_recv: u128


@error
class BatchError:
    SKIPPED = 1


@contract
class AtomicMultiSwapContract:
    """Match two lists of swap specs and invoke the atomic swap contract.

    try_void keeps a contract error from aborting the rest of the batch.
    An authorization failure still propagates. break is not available, so a
    matched counterparty is marked and skipped.
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
        caught: Result[None, u32] = Result[None, u32].err(BatchError.SKIPPED)
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
                                caught = swap_contract.try_void(
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
                                if caught.is_ok():
                                    used.set(index_b, True)
                                    matched = True
