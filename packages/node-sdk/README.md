# @neon3/sdk

Node.js and TypeScript client SDK for Neon3 `neon3.rpc` and `neon3.event`.

## Install

```powershell
npm install @neon3/sdk
```

Package page: https://www.npmjs.com/package/@neon3/sdk

## Start Neon3

`RuntimeSession` starts `neon-eventd`, `neon-wgpu-runtime`, and
`neon-ui-runtime` as separate processes. On Windows, it uses a local bundle or
resolves and downloads the latest runtime from the Neon3 GitHub Releases page:

https://github.com/unco999/Neon3-CiJian/releases

```ts
import { RuntimeSession } from "@neon3/sdk";

const runtime = new RuntimeSession({ mode: "windowed" });
await runtime.start();
try {
  console.log("Neon3 services are running");
} finally {
  await runtime.stop();
}
```

The resolved release is cached under `%LOCALAPPDATA%\\Neon3Sdk\\runtime\\<tag>`.
Set `NEON3_RUNTIME_VERSION=<tag>` (for example `v0.2.3`) when reproducible
pinning is required; only pin a runtime at least as new as the UI schema your
flows use, or newer nodes such as `tooltip` or `canvas` fail with
`nui_flow_unknown_attribute`. Set
`NEON_ROOT` or pass `neonRoot` to use a local checkout. `NEON_PROFILE` accepts
`auto`, `release`, or `debug`; `auto` prefers release binaries. The SDK never
creates a window or owns a GPU resource.

If GitHub is only reachable through a local HTTP proxy, set it before starting
the session. The SDK honors `HTTPS_PROXY`, `HTTP_PROXY`, and their lowercase
variants; loopback service traffic is not sent through the proxy.

```powershell
$env:HTTPS_PROXY = "http://127.0.0.1:7892"
$env:HTTP_PROXY = "http://127.0.0.1:7892"
```

## RPC Usage

```ts
import { NeonClient, UiClient } from "@neon3/sdk";

const ui = new UiClient(new NeonClient("127.0.0.1:39102", {
  origin: "my-node-tool",
}));
const program = await ui.submitFlow(
  "version 1\nsurface example revision 1\nsurface root\n",
);
console.log(program.surfaceId);
```

## Event Usage

```ts
import { EventClient } from "@neon3/sdk";

const events = await new EventClient("127.0.0.1:39101").subscribe({
  name: "ui.file_drop.accepted",
});
const imageDrop = await events.nextFileDrop();
console.log(imageDrop.payload);
events.close();
```

`ui.file_drop.accepted` is the existing Neon3 event bridge for OS file drops.
Image tools can use it to start OpenCV analysis without polling.

## Tests

```powershell
npm test
```
