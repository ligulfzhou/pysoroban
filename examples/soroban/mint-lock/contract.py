from pysoroban import (
    Address,
    Symbol,
    contract,
    error,
    fail,
    ledger,
    public,
    storage,
    struct,
    u128,
    u32,
)


@error
class MintError:
    NOT_AUTHORIZED_MINTER = 1
    DAILY_LIMIT_INSUFFICIENT = 2


@struct
class MinterConfig:
    limit: u128
    epoch_length: u32


@struct
class MinterKey:
    contract: Address
    minter: Address


@struct
class StatsKey:
    contract: Address
    minter: Address
    epoch_length: u32
    epoch: u32


@struct
class MinterInfo:
    limit: u128
    epoch_length: u32
    epoch: u32
    consumed: u128


@contract
class Contract:
    """Admin-controlled mint limits.

    Upstream keys are data-carrying enums and the minter query returns a tuple.
    Keys here are structs and minter() returns MinterInfo. Amounts are u128,
    so the negative-amount error does not apply. The admin may mint without a
    limit, matching the upstream bypass.
    """

    @public
    def initialize(self, admin: Address) -> None:
        storage.instance.set(Symbol("Admin"), admin)

    @public
    def set_admin(self, new_admin: Address) -> None:
        admin: Address = storage.instance.get_address(Symbol("Admin"))
        admin.require_auth()
        storage.instance.set(Symbol("Admin"), new_admin)

    @public
    def admin(self) -> Address:
        return storage.instance.get_address(Symbol("Admin"))

    @public
    def set_minter(self, contract: Address, minter: Address, config: MinterConfig) -> None:
        admin: Address = storage.instance.get_address(Symbol("Admin"))
        admin.require_auth()
        storage.persistent.set(MinterKey(contract, minter), config)

    @public
    def minter(self, contract: Address, minter: Address) -> MinterInfo:
        key: MinterKey = MinterKey(contract, minter)
        if not storage.persistent.has(key):
            fail(MintError.NOT_AUTHORIZED_MINTER)
        config: MinterConfig = storage.persistent.get(key, MinterConfig)
        epoch: u32 = ledger.sequence() // config.epoch_length
        consumed: u128 = u128(0)
        stats_key: StatsKey = StatsKey(contract, minter, config.epoch_length, epoch)
        if storage.temporary.has(stats_key):
            consumed = storage.temporary.get(stats_key, u128)
        return MinterInfo(config.limit, config.epoch_length, epoch, consumed)

    @public
    def mint(self, contract: Address, minter: Address, to: Address, amount: u128) -> None:
        minter.require_auth_for(contract, to, amount)
        admin: Address = storage.instance.get_address(Symbol("Admin"))
        if admin != minter:
            key: MinterKey = MinterKey(contract, minter)
            if not storage.persistent.has(key):
                fail(MintError.NOT_AUTHORIZED_MINTER)
            config: MinterConfig = storage.persistent.get(key, MinterConfig)
            epoch: u32 = ledger.sequence() // config.epoch_length
            stats_key: StatsKey = StatsKey(contract, minter, config.epoch_length, epoch)
            consumed: u128 = u128(0)
            if storage.temporary.has(stats_key):
                consumed = storage.temporary.get(stats_key, u128)
            updated: u128 = consumed + amount
            if updated > config.limit:
                fail(MintError.DAILY_LIMIT_INSUFFICIENT)
            storage.temporary.set(stats_key, updated)
            end_ledger: u32 = config.epoch_length * (epoch + u32(1)) - u32(1)
            storage.temporary.extend_ttl(stats_key, end_ledger, end_ledger)
        contract.call_void(Symbol("mint"), to, amount)
