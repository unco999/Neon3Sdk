# Neon3 SDK

Language clients for the [Neon3][] control-plane protocol (`neon3.rpc`).

Both SDKs speak the same canonical JSON-over-TCP framing (4 byte big-endian
length prefix). Neither creates a window, owns a GPU resource, or writes project
files — those remain the responsibility of the Neon3 runtime services.

## Repository layout

```
packages/
  python-sdk/          Python package: neon3-sdk
  node-sdk/            TypeScript/Node.js package: @neon3/sdk
```

## Quick start

### Python

```bash
cd packages/python-sdk
pip install -e .
python -m neon3_sdk calculator --neon-root <path-to-neon3-runtime>
```

Run the deterministic `1 + 2 = 3` scenario:

```bash
python -m neon3_sdk calculator --neon-root <path-to-neon3-runtime> --once
```

### TypeScript / Node.js

```bash
cd packages/node-sdk
npm install
npm run test
npm run calculator
```

Run the headless API-contract probe:

```bash
npm run probe
```

## Packages

| Package | Source | npm / PyPI | Protocol |
|---------|--------|------------|----------|
| `neon3-sdk` (Python) | `packages/python-sdk/` | PyPI | `neon3.rpc` |
| `@neon3/sdk` (Node) | `packages/node-sdk/` | npm | `neon3.rpc` |

Both expose the same logical API surface: `UiClient`, `RenderClient`, `InputClient`,
and `ExternalSurface` negotiation. See each package's README for full API docs.

## Boundaries

- **UiClient** — submit `.nui` flows, publish typed input frames, receive semantic
  host-inbound events, inspect UI snapshots and traces.
- **RenderClient** — diagnostics, graph snapshot, world configuration, 3D camera
  frames, pointer events, external-surface lifecycle.
- **InputClient** — typed pointer input and keyboard capability detection.
- **ExternalSurface** — Windows/DX12 shared texture descriptor, brokered handle
  acquisition, generation, frame sequence, and fence values. Language clients
  never interpret native handles or own GPU resources.

## Relationship to the Neon3 runtime

The Neon3 runtime (Rust + WGPU) is maintained in a separate repository. It
provides the `neon-wgpu-runtime`, `neon-ui-runtime`, and `neon-eventd` services
that these SDKs connect to over loopback TCP. The `--neon-root` flag in the
examples above points to a local checkout of that runtime.

## License

Licensed under either of [MIT](LICENSE-MIT) or [Apache 2.0](LICENSE-APACHE) at
your option. Individual package subdirectories each carry their own license
metadata.

[Neon3]: https://github.com/unco999/Neon3-CiJian