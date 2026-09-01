# Changelog

All notable changes to the Neon3 language SDKs are recorded in this file.

## 0.1.3 — 2026-09-01

### Fixed

- **The published packages now actually resolve the latest runtime.** Commit
  `ab802c2` introduced latest-release resolution, but it was never published:
  `neon3-sdk==0.1.2` on PyPI still hard-codes `NEON3_RUNTIME_VERSION = "v0.2.1"`.
  Any UI schema newer than the v0.2.1 runtime (for example `tooltip`, `rich`,
  `nine_slice`, `canvas`) failed at flow submission with
  `nui_flow_unknown_attribute`, because the SDK kept launching the pinned old
  bundle regardless of newer Neon3 releases.
- 0.1.3 publishes the already-committed latest-release resolution for both the
  Python and Node SDKs, so clients track `Neon3-CiJian` releases automatically.
  Pin a version explicitly with `NEON3_RUNTIME_VERSION` when reproducibility
  requires it.

### Verification

- Python package `neon3-sdk==0.1.3`: 9 unit tests passed; sdist and universal
  wheel built successfully.
- Node package `@neon3/sdk@0.1.3`: TypeScript build passed; 2 tests passed when
  the test files are named explicitly. The `npm test` script itself uses a
  shell glob (`dist/test/*.test.js`) that does not expand under Windows
  PowerShell, so it fails there; this is pre-existing, unrelated to 0.1.3.
- End-to-end with the real published chain: installing the 0.1.3 wheel into the
  example venv resolved `releases/latest` to **v0.2.3**, downloaded that bundle
  into `%LOCALAPPDATA%\Neon3Sdk\runtime\v0.2.3`, and the inventory example
  submitted its flow successfully (`pass_result: true`, capabilities including
  `ui.nine_slice.v1` and `ui.canvas.points_lines.v1`).
- Known limitation found during verification, on the runtime side rather than
  the SDK: `inventory.py --probe` needs a window target capture, and the
  release runtime only exposes capture in debug builds
  (`debug_endpoint_unavailable: window target capture is only available in
  debug builds`). Windowed mode works; the probe path needs either a debug
  runtime or a release-build capture capability.

## 0.1.2 — 2026-09-01

### Added

- Node.js and Python runtime sessions began resolving the Neon3 GitHub
  `releases/latest` endpoint in source (commit `ab802c2`) when no explicit
  `NEON3_RUNTIME_VERSION` was set. **Note:** this behavior was *not* in the
  published 0.1.2 packages — see the 0.1.3 Fixed section.
- Both SDKs download the resolved Windows runtime archive into the per-user
  cache and validate the three required service executables before startup:
  `neon-eventd`, `neon-wgpu-runtime`, and `neon-ui-runtime`.
- Node runtime downloads support the existing `HTTPS_PROXY`/`HTTP_PROXY`
  environment configuration through `undici`'s `ProxyAgent`.
- Added release-stack automation that can build a runtime bundle from a verified
  source checkout, run focused probes and package checks, and emit JSONL plus a
  JSON manifest.

### Changed

- Runtime startup now resolves release tags before calculating the cache path,
  preventing a literal `latest` cache directory from being treated as a release.
- `RuntimeSession` continues to prefer explicit `NEON_ROOT` source checkouts,
  then release binaries, then debug binaries, preserving deterministic local
  development behavior.
- Documentation now describes the latest-release behavior, runtime ownership
  boundary, proxy configuration, and event-stream integration for file drops.

### Verification

- Node package `@neon3/sdk@0.1.2`: TypeScript build passed; 2 tests passed;
  `npm pack --dry-run` produced a 37-file, 13.8 kB tarball.
- Python package `neon3-sdk==0.1.2`: 9 tests passed; sdist and universal wheel
  built successfully.

### Publication status

- Not published at the time of this entry. Both registries require credentials
  that are not present in this environment: the local `.npmrc` token is not a
  usable `@neon3` publisher, and there is no PyPI credential or `~/.pypirc`.
- Until 0.1.3 (or newer) is uploaded, `pip install neon3-sdk` and
  `npm install @neon3/sdk` still deliver the v0.2.1-pinned 0.1.2 packages.
  Workaround for affected users: pin `NEON3_RUNTIME_VERSION=v0.2.3`, or point
  `NEON_ROOT` at a local Neon3 checkout with release binaries.
