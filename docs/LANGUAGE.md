# PySoroban language specification

This document freezes the behavior of the current compiler. It is the
reference for integer semantics, overflow, and contract errors. A source
program accepted by this specification must keep compiling to the same
protocol-25 Wasm bytes until the specification itself changes. That lock is
enforced by `tests/test_bytecode_lock.py` for the compiler-suite fixtures
whose source did not change, and for a small integer corpus. The fixtures
are the former flat examples, kept out of `examples/` after that directory
became the soroban-examples ports.

The compiler still targets Stellar protocol 25. Dynamic Python, including
arbitrary objects, reflection, `eval`, floating point, exceptions, generators,
and unbounded recursion, is rejected. PySoroban does not promise CPython
evaluation order beyond what this document states.

## Diagnostics

`CompileError.code` is a stable `E####` identifier. The human message may be
clarified, but a code keeps its meaning. Location is 1-based line and column
when the parser has a node. Codes are grouped as follows:

| Range | Meaning |
| --- | --- |
| `E0001`–`E0002` | Python syntax, or not exactly one `@contract` class |
| `E0101`–`E0110` | Function shape and return checking |
| `E0201`–`E0211` | Type annotations |
| `E0301`–`E0309` | Events |
| `E0401`–`E0412` | Statements |
| `E0501`–`E0518` | Expressions |
| `E0601`–`E0665` | Calls, storage, and cross-contract invocations |
| `E0701`–`E0715` | `@error` and `fail` |
| `E0801`–`E0825` | `@struct`, `@enum`, and `@union` |
| `E0641`–`E0648` | storage tiers, `get(key, Type)`, and collection updates |
| `E9001`–`E9003` | Internal lowering failure after a frontend bug |

## Types and literals

Supported value types are `i32`, `u32`, `i64`, `u64`, `i128`, `u128`, `u256`,
`boolean`, `Address`, `Symbol`, `String`, `Bytes`, and `None` (`void`).
`Vec[T]` is homogeneous. The element may be one of those scalars, `BytesN[N]`,
another `Vec` or `Map`, `Option`, `Result`, `Tuple`, or a user-defined
`@struct`, `@enum`, or `@union`. `BytesN[N]` is a byte string of length `N`
(1 through 1024). BLS points use 96 and 192. `Map[K, V]` accepts scalar, enum, and struct keys. Values may
be nested collections. Map keys may not be collections. `Bytes` and `BytesN`
support ordering comparisons. `to_xdr(value)` returns the Soroban ScVal XDR
bytes.
`u256.to_be_bytes()` and `u256.from_be_bytes(data)` convert the raw 32-byte
integer. `address.to_strkey()` asks the host for the `G...` or `C...` form.

A `@struct` is a named record stored as a Soroban map from field symbol to
value. An `@enum` is a named `u32` discriminant. A `@union` is a data-carrying
enum. A case written `name: None` is only the case symbol. A case written
`name: T` is a vector of that symbol and one payload. A payload may itself be
a `Tuple`. A variant with several fields is a `@struct` payload. Directly
recursive struct fields and union cases are rejected.

`Option[T]` is `Option.none()` or `Option.some(value)`. `Option.none()` needs
an `Option[T]` annotation. `Option[None]` is rejected. `value.is_some()` is
`boolean`. `value.unwrap()` traps when the option is empty.

`Result[T, u32]` is `Result[T, u32].ok(value)` or
`Result[T, u32].err(Error.CASE)`. The error side is the case's `u32` code.
`value.is_ok()`, `value.unwrap()`, and `value.unwrap_err()` follow the same
rule: unwrapping the wrong side traps. `T` may be `None`.

`Tuple[A, B](a, b)` is a fixed vector of 1 to 12 values. `pair[0]` requires
an in-range integer literal. `Val` is an untyped Soroban value and is passed
through unchanged.

A bare integer literal is `i32` and must lie in `[-2^31, 2^31)`. `True` and
`False` are `boolean`. Wider integers and host objects are constructed from
literals: `u64(1)`, `Symbol("name")`, `String("text")`, `Bytes(b"...")`.
Those constructors are not runtime casts. `Symbol` literals are at most 32
bytes and use only `[A-Za-z0-9_]`.

## Integer semantics

Arithmetic requires both operands to have the same numeric type. `and` / `or`
are allowed only on `boolean`. Comparisons require the same type. Ordering
(`<`, `>`, `<=`, `>=`) is allowed only for the integer types. Other types
support `==` and `!=` only. Chained comparisons are rejected.

`and` and `or` evaluate both operands. They are Wasm `i32.and` / `i32.or`,
not short-circuiting Python operators.

| Type | `+`, `-`, `*` | `//` | Division by zero | Overflow |
| --- | --- | --- | --- | --- |
| `i32` | wrap modulo `2^32`, then interpret as signed | rejected | — | wrap |
| `u32` | wrap modulo `2^32` | unsigned floor division | trap | wrap |
| `i64` | wrap modulo `2^64`, then interpret as signed | rejected | — | wrap |
| `u64` | wrap modulo `2^64` | unsigned floor division | trap | wrap |
| `i128` | checked `+`, `-`, and `*` | checked floor division | trap | trap |
| `u128` | checked `+`, `-`, and `*` | checked unsigned floor division | trap | trap |
| `u256` | checked `+`, `-`, and `*` | checked unsigned floor division | trap | trap |

Unary minus is defined for `i32` and `i64` and uses the same wrapping
subtraction from zero. It is rejected for unsigned types and for `i128`.
Unary `not` is defined for `boolean` only.

`i128` and `u128` live in Soroban `Val` objects, not in Wasm integer locals.
Checked addition and subtraction trap by executing Wasm `unreachable` when the
signed `i128` sign bit disagrees with the operands, or when a `u128` result
would wrap. That trap is a Wasm trap, not a contract-error code.

`u128` multiplication widens both operands to `u256`, multiplies with the
protocol-25 host (`i.p`), and traps when either high 128-bit half is nonzero.
`u128` floor division uses the same widening and the host divide (`i.q`), which
traps on a zero divisor. `i128` multiplication sign-extends into `i256`,
multiplies with `i.x`, and traps unless the high half is the sign extension of
bit 127. `i128` floor division sign-extends into `i256` and divides with
`i.y`, which truncates toward zero and traps on a zero divisor. When that
quotient is inexact and the operand signs differ, the compiler subtracts one
with `i.w`, matching Python `//`. The quotient is then narrowed like `i128`
multiplication, so `i128` minimum divided by `-1` traps.

`u256(...)`, like the other integer constructors, accepts an integer literal or a
constant expression built from literals with `+`, `-`, `*`, and `**`.
`u256` values are host objects. Addition, subtraction, multiplication, and
floor division call the protocol checked `u256` operations (`i.n`, `i.o`,
`i.p`, `i.q`). Overflow and division by zero trap inside the host. Literals
use `u256(...)` and `obj_from_u256_pieces`.

`u128.mul_div_floor(left, right, denominator)` computes
`floor((left * right) / denominator)` with a `u256` intermediate using the
same host multiply and divide. A zero denominator traps inside that host
divide. If the quotient does not fit in `u128`, the compiler emits
`unreachable`. Rounding is toward zero, which is floor for unsigned values.

Asset accounting must use the checked `u128` operations. Wrapping `i32` /
`u32` / `i64` / `u64` arithmetic is intentional and is not a contract error.

## Control flow

`if` / `else` and `return` are supported. A non-void function must return or
`fail` on every path. `for` accepts only `range(stop)` and `range(start, stop)`
with `i32` bounds and an implicit step of `+1`. The stop is exclusive. The
loop variable is `i32`. Variables assigned in the body must already exist.
`break`, `continue`, `for` / `else`, `while`, and recursion are rejected.

## Storage, authorization, calls, and events

`storage.instance`, `storage.persistent`, and `storage.temporary` all
support `set`, `has`, `remove`, and the typed getters `get_i32`, `get_u32`,
`get_i64`, `get_u64`, `get_i128`, `get_u128`, `get_bool`, `get_symbol`,
`get_string`, `get_bytes`, and `get_address`. `get(key, Type)` reads any
supported type, including `Vec`, `Map`, `@struct`, and `@enum`. A missing
key traps in the host; the test environment raises `StorageMissingError`.
`storage.persistent.extend_ttl(key, threshold, extend_to)` and the same
method on `storage.temporary` call `extend_contract_data_ttl`.
`storage.instance.extend_ttl(threshold, extend_to)` extends the current
contract instance and code. The test environment records those requests on
`ttl_extensions` and does not simulate ledger expiry.

Cross-contract calls are `call_void`, `call_i32`, `call_u32`, `call_i64`,
`call_u64`, `call_i128`, `call_u128`, `call_u256`, `call_bool`, `call_address`,
`call_symbol`, `call_string`, and `call_bytes`. The first argument is a
`Symbol` function name. There is no `call_vec` or `call_map`.

`try_void`, `try_i32`, `try_u32`, `try_i64`, `try_u64`, `try_i128`,
`try_u128`, `try_u256`, `try_bool`, `try_address`, `try_symbol`, `try_string`,
and `try_bytes` have the same arguments and return `Result[T, u32]`. A callee
`fail` becomes the error code. The test host rolls that callee back and
continues the caller. Other failures, including a missing authorization, still
propagate. On the network the host returns the success value or an error
`Val`; `unwrap_err` reads that error code. The test host stores
`("ok", value)` or `("err", code)` instead, so these values are not part of
the differential suite.

`len(values)` returns `i32` for `Vec`, `Map`, `String`, and `Bytes`. The host
length is a `u32`; values above `2^31 - 1` are not representable as that
`i32`. `Vec` supports `values[index]` with an `i32` index. `Map` supports
`has` and indexing. Slicing a `Vec` or `Map` is rejected. Empty collections are
`values: Vec[T] = Vec()` and `mapping: Map[K, V] = Map()`. Updates are
statements that replace the local: `values.push(item)`,
`values.set(index, item)`, `values.insert(index, item)`,
`values.remove(index)`, `mapping.set(key, value)`, and `mapping.remove(key)`.
`item = values.pop()` removes the last element and binds it. These methods
are not expressions. The host operations return a new collection; the
compiler writes that handle back to the local.

`String.to_bytes()` and `Bytes.to_string()` convert UTF-8. Invalid UTF-8 traps.
`Bytes.slice(start, end)` takes `u32` bounds and excludes `end`. A range outside
the buffer traps. `value.append(other)` is a statement, like `Vec.push`.

`ledger.sequence()`, `ledger.version()`, and `ledger.max_live_until()` return
`u32`. `ledger.timestamp()` returns `u64`. `ledger.network_id()` returns `Bytes`.
`env.current_contract_address()` returns `Address`. `ledger.max_live_until()`
is host `x.8`.

`crypto.sha256(value)` and `crypto.keccak256(value)` hash `Bytes` and return
`Bytes`. `crypto.ed25519_verify(key, message, signature)` takes three `Bytes`
or `BytesN` values and returns `None`; a rejected signature traps.
Protocol 25 also exposes BLS12-381 and BN254 through `crypto.<host name>(...)`,
including `bls12_381_hash_to_g2`, `bls12_381_multi_pairing_check`,
`bls12_381_fr_*`, `bn254_g1_add`, `bn254_g1_mul`, and
`bn254_multi_pairing_check`. Points are `Bytes` or `BytesN`. Scalars are
`u256`, except `fr_pow`, whose exponent is `u64`. Pairing and MSM arguments
are `Vec[Bytes]` or `Vec[u256]`. A `Vec[Bytes]` element may be `BytesN`.
Protocol 26 names such as `bn254_fr_add` and the on-curve checks are not
imported. `log(message)` writes one `String`. `prng.bytes(length)` takes a
`u32` and returns `Bytes`. `prng.u64(low, high)` takes an inclusive `u64`
range and returns `u64`.

`address.require_auth()` traps unless that address authorized the invocation.
`address.require_auth_for(*args)` does the same and passes the authorized
argument vector to the host. The test environment accepts an address in the
call's `auth` list. A direct cross-contract call also authorizes the calling
contract, which is how a contract spends its own token balance. That caller is
not authorized for a further nested call. `ContractTest.authorize_account`
stores a payload, a signature, and contexts. `require_auth` for that address
then runs the registered contract's `__check_auth`. The test host does not
derive `Context` from the call stack.

`auth.as_current_contract(contract, fn_name, argument)` authorizes one deeper
`require_auth` of the current contract for that function and argument. Wasm
builds one `InvokerContractAuthEntry::Contract` value: a vector of the symbol
`Contract` and a map with `context` (`contract`, `fn_name`, `args`) and an
empty `sub_invocations` vector. It calls host `a.3`.

`i128.from_val(value)` and the same method on the other integer types and
`Address` read a `Val`. In Wasm the bits stay a `Val` for object types and are
decoded for 32-bit and 64-bit integers. `Vec[Val]` is allowed.

`deploy.upload(wasm)` returns the `Bytes` hash of a Wasm payload.
`deploy.contract(wasm_hash, salt)` and
`deploy.with_constructor(wasm_hash, salt, *args)` return the new `Address`.
`deploy.upgrade(wasm_hash)` replaces the current contract Wasm.
`deploy.asset(serialized_asset)` creates a Stellar Asset Contract from the
serialized asset bytes and returns its `Address`. The compiler does not build
that asset XDR.

The test environment is not the Soroban host. It records TTL extensions.
`enforce_ttl` is off by default, so entries stay readable. When it is on, a
ledger sequence past the recorded live-until ledger makes `has` return false
and `get` raise. A missing bound is treated as due for extension. The new
bound is `sequence + extend_to`, clamped to `max_live_until_ledger`.
`ed25519_verify` accepts a triple from `allow_signature` first. Otherwise it
uses the `cryptography` package when that package is installed.
`prng` is a local xorshift, not the host PRNG. Deployed addresses are
synthetic, while `deploy.upload` returns a real SHA-256 digest. `try_*`
catches `fail` in the callee and rolls that callee back. Curve calls return
the next value queued by `allow_host_result`; the test host does not evaluate
BLS12-381 or BN254. The host does not build create-contract `Context`
variants or auth trees deeper than one subcall.

Typed events use `@event`, exactly one data field, and `Topic[T]` fields
before that data field. `events.publish` also accepts a raw `Symbol` topic
plus one data value.

## Contract errors

```python
@error
class SwapError:
    SLIPPAGE = 1

fail(SwapError.SLIPPAGE)
```

`@error` is a module-level enum. Each case is `NAME = <u32 literal>`. Values
must be unique and in `[0, 2^32)`. Names are at most 60 UTF-8 bytes. The enum
is written to `contractspecv0` as `SC_SPEC_ENTRY_UDT_ERROR_ENUM_V0` (kind 4),
so Stellar CLI can read the case names and values.

`fail` is valid only as an expression statement. It ends the current path, so
a branch that fails does not also need to return. It lowers to host import
`x.5` (`fail_with_error`) with a Soroban `Error` value:

- tag `3` (`Tag::Error`);
- minor `0` (`ScErrorType::Contract`);
- major equal to the case value.

The bits are `(code << 32) | 3`. The call is followed by Wasm `unreachable`.
The import is emitted only when the contract contains `fail`, so contracts
that do not fail keep their previous bytes.

On a real Soroban host, `fail_with_error` traps the contract and the host
discards the invocation's ledger writes. The Python test environment does the
same for every `InvocationError` raised by the root call, including
`ContractError`, `AuthorizationError`, `StorageMissingError`, overflow, and
division by zero. Events published during that call are discarded. Linked
contracts invoked as part of the call are restored too. `fail` is not a value.
A direct caller cannot catch it. `try_*` on another contract turns that
contract's `fail` into a `Result` error.

Returning `0` or `u128(0)` is a successful result. It does not roll anything
back. Use `fail` when a call must not commit. View functions may still return
zero to mean "absent", which is what `Counter.value` and the AMM reserve
getters do.
