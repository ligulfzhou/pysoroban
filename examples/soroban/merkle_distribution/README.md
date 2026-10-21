# merkle_distribution

Verification hashes the XDR encoding of a leaf and orders raw hash bytes. PySoroban can call SHA-256, but it has no `to_xdr`, no `Bytes` ordering, and no conversion from `Address` or integers into `Bytes`.
