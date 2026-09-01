# Neon3 SDK

Python and Node.js clients for the [Neon3](https://github.com/unco999/Neon3-CiJian)
control-plane protocols: `neon3.rpc` and `neon3.event`.

## Downloads

- Python: [neon3-sdk on PyPI](https://pypi.org/project/neon3-sdk/)
- Node.js: [@neon3/sdk on npm](https://www.npmjs.com/package/@neon3/sdk)
- Runtime: [Neon3 GitHub Releases](https://github.com/unco999/Neon3-CiJian/releases)

```powershell
python -m pip install --upgrade neon3-sdk
npm install @neon3/sdk
```

## Runtime

The SDK starts the separate `neon-eventd`, `neon-wgpu-runtime`, and
`neon-ui-runtime` processes. WGPU resources and the window remain owned by
`neon-wgpu-runtime`; the language clients never create GPU objects.

On Windows, `RuntimeSession` uses the local SDK bundle when available. Otherwise
it resolves and downloads the latest runtime asset from the Neon3 GitHub
Releases page and caches it under `%LOCALAPPDATA%\Neon3Sdk\runtime\<tag>`.
Set `NEON3_RUNTIME_VERSION=<tag>` (for example `v0.2.3`) when reproducible
pinning is required; pin only a runtime at least as new as the UI schema your
flows use, or newer nodes such as `tooltip` or `canvas` fail with
`nui_flow_unknown_attribute`. Runtime binaries are
kept out of the PyPI/npm packages.

Python:

```python
from neon3_sdk import RuntimeConfig, RuntimeMode, RuntimeSession

with RuntimeSession(RuntimeConfig(mode=RuntimeMode.WINDOWED)):
    # Use NeonClient, UiClient, RenderClient, or EventClient here.
    pass
```

Node.js:

```ts
import { RuntimeSession } from "@neon3/sdk";

const runtime = new RuntimeSession({ mode: "windowed" });
await runtime.start();
try {
  // Use NeonClient, UiClient, RenderClient, or EventClient here.
} finally {
  await runtime.stop();
}
```

For a source checkout or CI build, set `NEON_ROOT`. `NEON_PROFILE` accepts
`auto`, `release`, or `debug`; `auto` prefers release binaries.

```powershell
$env:NEON_ROOT = "D:\Neon3"
$env:NEON_PROFILE = "debug"
```

When GitHub access requires a local HTTP proxy, set `HTTPS_PROXY` and
`HTTP_PROXY`, for example `http://127.0.0.1:7892`. The SDK uses the proxy only
for runtime bundle downloads; Neon3 loopback RPC remains local.

## Event Stream

Both SDKs expose the existing `neon3.event` stream. File-drop tools can listen
for `ui.file_drop.accepted` and start image analysis without polling or a second
transport.

Python:

```python
from neon3_sdk import EventClient

with EventClient.connect("127.0.0.1:39101").subscribe(
    name="ui.file_drop.accepted"
) as events:
    for image in events.file_drops():
        print(image.source_path)
```

Node.js:

```ts
import { EventClient } from "@neon3/sdk";

const events = await new EventClient("127.0.0.1:39101").subscribe({
  name: "ui.file_drop.accepted",
});
const imageDrop = await events.nextFileDrop();
events.close();
```

## Development

```powershell
cd packages\python-sdk
python -m unittest discover -s tests -v

cd ..\node-sdk
npm test
```

The runtime release is intentionally separate from the language packages. This
keeps installation small while preserving the Neon3 multi-process boundary.

## Maintainer release pipeline

Canvas renderer changes live in the Neon3 runtime; the Python and Node SDK
sources only need a release when their public protocol/client API changes. Once
Neon3 has a committed, pushed and tagged release commit, run the cross-repo
validation and bundle pipeline:

```powershell
& D:\Neon3Sdk\scripts\sync-neon3-stack.ps1 -ReleaseRef v0.2.2 -BuildRuntime
```

It runs the real `canvas_window_probe` (NUI producer -> IPC -> WGPU window
consumer), workspace/package checks, SDK tests and the Bevy plugin check. It
emits JSONL while running and writes
`release/neon3-stack-validation.json`. It refuses to build a distributable SDK
runtime if Neon3 is dirty, ahead of upstream, or the supplied release tag does
not identify the tested Neon3 `HEAD`. For a new runtime release, first update
both SDK `NEON3_RUNTIME_VERSION` constants (Python and Node) to the release tag
only when a reproducible pin is required; `latest` is also accepted. The
pipeline verifies the selection before bundling. The script never commits, pushes,
tags or publishes packages; those remain an
explicit release approval step.
