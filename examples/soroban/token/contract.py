from pysoroban import Address, String, Symbol, contract, error, events, fail, public, storage, struct, u128, u32


@error
class TokenError:
    ALREADY_INITIALIZED = 1
    NOT_INITIALIZED = 2
    INSUFFICIENT_BALANCE = 3
    INSUFFICIENT_ALLOWANCE = 4
    INVALID_AMOUNT = 5


@struct
class Allowance:
    owner: Address
    spender: Address


@contract
class Token:
    """SEP-41 style token corresponding to stellar/soroban-examples token.

    That example is the Rust SDK token implementation split across modules.
    This contract covers the same balance, allowance, mint, and burn surface
    with checked u128 amounts. It is not the Stellar Asset Contract. The host
    still creates SAC instances through deploy.asset(), which takes serialized
    asset bytes this compiler does not build.
    """

    @public
    def initialize(self, admin: Address, decimals: u32, name: String) -> None:
        admin.require_auth()
        if storage.instance.has(Symbol("admin")):
            fail(TokenError.ALREADY_INITIALIZED)
        storage.instance.set(Symbol("admin"), admin)
        storage.instance.set(Symbol("decimals"), decimals)
        storage.instance.set(Symbol("name"), name)

    @public
    def decimals(self) -> u32:
        return storage.instance.get_u32(Symbol("decimals"))

    @public
    def name(self) -> String:
        return storage.instance.get_string(Symbol("name"))

    @public
    def balance(self, id: Address) -> u128:
        if storage.persistent.has(id):
            return storage.persistent.get(id, u128)
        return u128(0)

    @public
    def allowance(self, owner: Address, spender: Address) -> u128:
        key: Allowance = Allowance(owner, spender)
        if storage.persistent.has(key):
            return storage.persistent.get(key, u128)
        return u128(0)

    @public
    def transfer(self, from_account: Address, to: Address, amount: u128) -> None:
        from_account.require_auth()
        self_balance: u128 = u128(0)
        if storage.persistent.has(from_account):
            self_balance = storage.persistent.get(from_account, u128)
        if self_balance < amount:
            fail(TokenError.INSUFFICIENT_BALANCE)
        storage.persistent.set(from_account, self_balance - amount)
        destination: u128 = u128(0)
        if storage.persistent.has(to):
            destination = storage.persistent.get(to, u128)
        storage.persistent.set(to, destination + amount)
        events.publish(Symbol("transfer"), amount)

    @public
    def approve(self, owner: Address, spender: Address, amount: u128) -> None:
        owner.require_auth()
        storage.persistent.set(Allowance(owner, spender), amount)

    @public
    def transfer_from(self, spender: Address, from_account: Address, to: Address, amount: u128) -> None:
        spender.require_auth()
        key: Allowance = Allowance(from_account, spender)
        allowed: u128 = u128(0)
        if storage.persistent.has(key):
            allowed = storage.persistent.get(key, u128)
        if allowed < amount:
            fail(TokenError.INSUFFICIENT_ALLOWANCE)
        storage.persistent.set(key, allowed - amount)
        balance: u128 = u128(0)
        if storage.persistent.has(from_account):
            balance = storage.persistent.get(from_account, u128)
        if balance < amount:
            fail(TokenError.INSUFFICIENT_BALANCE)
        storage.persistent.set(from_account, balance - amount)
        destination: u128 = u128(0)
        if storage.persistent.has(to):
            destination = storage.persistent.get(to, u128)
        storage.persistent.set(to, destination + amount)

    @public
    def mint(self, to: Address, amount: u128) -> None:
        admin: Address = storage.instance.get_address(Symbol("admin"))
        admin.require_auth()
        current: u128 = u128(0)
        if storage.persistent.has(to):
            current = storage.persistent.get(to, u128)
        storage.persistent.set(to, current + amount)

    @public
    def burn(self, from_account: Address, amount: u128) -> None:
        from_account.require_auth()
        current: u128 = u128(0)
        if storage.persistent.has(from_account):
            current = storage.persistent.get(from_account, u128)
        if current < amount:
            fail(TokenError.INSUFFICIENT_BALANCE)
        storage.persistent.set(from_account, current - amount)
