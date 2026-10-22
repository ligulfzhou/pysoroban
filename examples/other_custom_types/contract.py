from pysoroban import (
    Address,
    Bytes,
    BytesN,
    Map,
    Option,
    Result,
    String,
    Symbol,
    Topic,
    Tuple,
    Val,
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
    union,
    i32,
    i64,
    i128,
    u32,
    u64,
    u128,
    u256,
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


@struct
class AssetBalance:
    """One-payload stand-in for a two-field enum variant."""

    token: Address
    amount: i128


@struct
class TupleStruct:
    value: Test
    simple: SimpleEnum


@union
class ComplexEnum:
    Struct: Test
    Tuple: TupleStruct
    Enum: SimpleEnum
    Asset: AssetBalance
    Void: None


@union
class ComplexEnum2:
    Stellar: Address
    Other: Symbol


@union
class ComplexEnum3:
    Some: Tuple[Address, i128]
    Empty: None


@struct
class ComplexStruct:
    admin: Address
    a64: u64
    assets_vec: Vec[ComplexEnum2]
    base_asset: ComplexEnum2
    a32: u32
    b32: u32
    c32: u32
    complex_enum3: ComplexEnum3


@contract
class CustomTypesContract:
    """Echo functions for the types PySoroban can pass across the ABI.

    `i256` is not a contract type. A two-field enum variant is a struct payload.
    The `None` variant is named `Empty` because `None` is not a Python name.
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

    @public
    def bytes_n(self, value: BytesN[9]) -> BytesN[9]:
        return value

    @public
    def tuple(self, pair: Tuple[Symbol, u32]) -> Tuple[Symbol, u32]:
        return pair

    @public
    def option(self, value: Option[u32]) -> Option[u32]:
        return value

    @public
    def odd(self, value: u32) -> Result[u32, u32]:
        half: u32 = value // u32(2)
        if half * u32(2) == value:
            return Result[u32, u32].err(Error.NUMBER_MUST_BE_ODD)
        return Result[u32, u32].ok(value)

    @public
    def u256_(self, value: u256) -> u256:
        return value

    @public
    def val_(self, value: Val) -> Val:
        return value

    @public
    def complex(self, value: ComplexEnum) -> ComplexEnum:
        return value

    @public
    def tuple_strukt(self, value: TupleStruct) -> TupleStruct:
        return value

    @public
    def complex_struct(self, value: ComplexStruct) -> ComplexStruct:
        return value
