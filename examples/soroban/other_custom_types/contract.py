from pysoroban import (
    Address,
    Bytes,
    Map,
    String,
    Symbol,
    Topic,
    Vec,
    boolean,
    contract,
    enum,
    error,
    event,
    events,
    fail,
    public,
    storage,
    struct,
    i32,
    i64,
    i128,
    u32,
    u64,
    u128,
)


@error
class Error:
    NUMBER_MUST_BE_ODD = 1


@struct
class Test:
    a: u32
    b: boolean
    c: Symbol


@enum
class SimpleEnum:
    FIRST = 0
    SECOND = 1
    THIRD = 2


@enum
class RoyalCard:
    JACK = 11
    QUEEN = 12
    KING = 13


@event
class AuthEvent:
    hello: Topic[Address]
    world: Symbol


@contract
class CustomTypesContract:
    """Echo functions for the types PySoroban can pass across the ABI.

    Not ported from the upstream file: Val, Result, Option, tuples, U256, I256,
    BytesN, data-carrying enums, and tuple structs. See examples/soroban/README.md.
    """

    @public
    def hello(self, hello: Symbol) -> Symbol:
        return hello

    @public
    def auth(self, addr: Address, world: Symbol) -> Address:
        addr.require_auth()
        events.publish(AuthEvent(addr, world))
        return addr

    @public
    def get_count(self) -> u32:
        if storage.persistent.has(Symbol("COUNTER")):
            return storage.persistent.get(Symbol("COUNTER"), u32)
        return u32(0)

    @public
    def inc(self) -> u32:
        count: u32 = u32(0)
        if storage.persistent.has(Symbol("COUNTER")):
            count = storage.persistent.get(Symbol("COUNTER"), u32)
        count = count + u32(1)
        storage.persistent.set(Symbol("COUNTER"), count)
        return count

    @public
    def woid(self) -> None:
        pass

    @public
    def u32_fail_on_even(self, value: u32) -> u32:
        half: u32 = value // u32(2)
        if half * u32(2) == value:
            fail(Error.NUMBER_MUST_BE_ODD)
        return value

    @public
    def u32_(self, value: u32) -> u32:
        return value

    @public
    def i32_(self, value: i32) -> i32:
        return value

    @public
    def i64_(self, value: i64) -> i64:
        return value

    @public
    def strukt(self, value: Test) -> Test:
        return value

    @public
    def simple(self, value: SimpleEnum) -> SimpleEnum:
        return value

    @public
    def addresse(self, value: Address) -> Address:
        return value

    @public
    def bytes_(self, value: Bytes) -> Bytes:
        return value

    @public
    def card(self, value: RoyalCard) -> RoyalCard:
        return value

    @public
    def boolean_(self, value: boolean) -> boolean:
        return value

    @public
    def not_(self, value: boolean) -> boolean:
        if value:
            return False
        return True

    @public
    def i128_(self, value: i128) -> i128:
        return value

    @public
    def u128_(self, value: u128) -> u128:
        return value

    @public
    def multi_args(self, a: u32, b: boolean) -> u32:
        if b:
            return a
        return u32(0)

    @public
    def map_(self, value: Map[u32, boolean]) -> Map[u32, boolean]:
        return value

    @public
    def vec_(self, value: Vec[u32]) -> Vec[u32]:
        return value

    @public
    def string_(self, value: String) -> String:
        return value
