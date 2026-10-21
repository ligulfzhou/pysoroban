# eth_abi

The contract decodes an Ethereum ABI blob with alloy and adds two `U256` values. PySoroban has no `U256`/`I256` type, no ABI decoder, and no arbitrary copy between `Bytes` and linear memory.
