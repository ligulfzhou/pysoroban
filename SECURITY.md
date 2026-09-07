# Security Policy

## Release status

PySoroban is experimental compiler infrastructure. The `0.9.0a1` release has
not completed an independent security audit and must not be used to control
production funds.

Generated contracts should be reviewed and tested like contracts produced by
any other compiler. Stellar testnet execution remains the integration source of
truth for the supported language surface.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
**Security → Report a vulnerability** workflow for the repository. Do not open
a public issue containing exploit details or sensitive information.

Include the PySoroban version, source contract, generated Wasm hash, expected
behavior, observed behavior, and a minimal reproduction when possible.
