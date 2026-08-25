# @neon3/sdk

TypeScript/Node.js client for Neon3's canonical `neon3.rpc` protocol.

```ts
import { NeonClient, RenderClient, UiClient } from "@neon3/sdk";

const rpc = new NeonClient("127.0.0.1:39102", { origin: "my-node-tool" });
const ui = new UiClient(rpc);
const program = await ui.submitFlowFile("./calculator.nui");

const renderer = new RenderClient(
  new NeonClient("127.0.0.1:39103", { origin: "my-node-tool" }),
);
await renderer.configureWorld({ worldSpaceId: "main-world", revision: 1 });
await renderer.submitCamera({
  cameraId: "editor-camera",
  worldSpaceId: "main-world",
  position: [0, 2, 5],
  orientationXyzw: [0, 0, 0, 1],
  verticalFovRadians: 1,
  near: 0.1,
  far: 1000,
  producerEpoch: 1,
  sequence: 1,
});
```

`RuntimeSession` starts windowed, headless, or external-surface Neon3 services.
Native GPU handles are returned only as brokered descriptors and are never
interpreted by the JavaScript layer.

Run the real headless probe with `npm run probe`. Set `NEON_EXTERNAL=1` to run
the Windows/DX12 external-surface probe instead.

The keyboard method is capability-gated. Until Neon3 advertises
`wgpu.ui.keyboard.v1`, `InputClient.keyboard()` returns the stable
`keyboard_capability_unavailable` error. Pointer input and external surface
protocols are available.

## Modular calculator example

```text
src/examples/calculator/
  domain.ts       calculator state machine and revisioned publication
  rpc-service.ts  Node domain RPC service
  flow.ts         loads calculator.nui
  calculator.nui  declarative UI only
  app.ts          process lifecycle and protocol wiring
```

Run the visible example:

```powershell
npm run calculator
```

Run the deterministic `1 + 1 = + 1 = 3` scenario:

```powershell
npm run calculator:once
```

The application keeps the calculator domain in `domain.ts`; the RPC listener
is in `rpc-service.ts`; `flow.ts` loads the declarative NUI; and `app.ts` only
connects the runtime, UI client, renderer, and domain service. This keeps
application logic out of the reusable SDK package.
