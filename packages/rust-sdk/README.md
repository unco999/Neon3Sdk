# Neon3 Rust SDK

Rust client SDK for the Neon3 control-plane protocol. Talks the same
`neon3.rpc` wire contract as the Python and Node SDKs over loopback TCP
(4-byte big-endian length prefix + UTF-8 JSON), so it works against the
desktop runtime, the headless GPU server, and the Android host endpoint.
