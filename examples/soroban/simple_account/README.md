# simple_account

Ed25519 verification is available as `crypto.ed25519_verify`, but `require_auth` does not call `__check_auth`. The signature payload and `Vec<Context>` arguments of that entry point are also missing.
