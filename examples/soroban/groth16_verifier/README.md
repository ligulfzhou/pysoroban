# groth16_verifier

Protocol 25 exposes `crypto.bn254_g1_add`, `crypto.bn254_g1_mul`, and
`crypto.bn254_multi_pairing_check`. This example is still not a Python port.
It verifies one prepared Groth16 circuit with arkworks, including a large
verifying key and proof layout. Those objects are not a short sequence of the
host calls. The test host does not evaluate BN254. Protocol 26 BN254 scalar
arithmetic is outside the protocol this compiler emits.
