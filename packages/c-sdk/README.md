# Neon3 C SDK (neon3-c)

C ABI library for the Neon3 control-plane protocol. Links the Rust core
(`neon3-sdk`) and exports a stable C interface for engines written in C or
other FFI hosts. Define `NEON3_C_STATIC` before including `neon3.h` when
linking the static library.

## Build

```powershell
cargo build -p neon3-c --release
```

Produces `neon3_c.dll` (Windows), `libneon3_c.so` (Linux), or
`libneon3_c.dylib` (macOS), plus `neon3_c.lib`/`libneon3_c.a` for static.
