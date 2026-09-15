# Neon3 Node.js / TypeScript SDK

Node.js client SDK for the Neon3 control-plane protocol. Talks the same
`neon3.rpc` wire contract as the Python and Rust SDKs over loopback TCP.

## Install

```bash
npm install @neon3/sdk
```

Or from source:

```bash
cd packages/node-sdk
npm install && npm run build
```

## Quick start (facade, recommended)

```ts
import { start, mount, state, on } from "@neon3/sdk";

const app = await start({ mode: "windowed", origin: "demo" });
await mount("counter.nui");
const count = state(0);

on("btn.increment", () => {
  count.value++;
});
```

### Renderer features

```ts
const app = await start();

// Shader events
app.shader.on(0x5F3759DF, (payload) => {
  console.log("energy:", payload[0]);
});

// View extras (60 Hz throttled)
app.renderer.viewExtras([0.1, 0.2, 0.3, 0.4]);

// Animation
await app.anim.seek("hero.timeline", 0.5);

// Offscreen screenshot
const png = await app.surface.render("hello.nui", { size: [1280, 720] });
await png.save("out.png");
```

## Low-level API

```ts
import { NeonClient, RenderClient, UiSession } from "@neon3/sdk";

const client = await NeonClient.connect("127.0.0.1:39102", { origin: "demo" });
const session = new UiSession(client);
await session.mountFlow(await readFile("hello.nui", "utf-8"));

const render = new RenderClient(
  await NeonClient.connect("127.0.0.1:39103", { origin: "demo" }),
);
await render.setViewExtras([[0.1, 0.2, 0.3, 0.4]]);
await render.animationPause("hero.timeline");
```

## Constants & enums

```ts
import { service, method, AnimationAction } from "@neon3/sdk";

client.call(service.WGPU_RUNTIME, method.WGPU_UI_SET_VIEW_EXTRAS, {...});
client.call(service.WGPU_RUNTIME, AnimationAction.Pause, {...});
```

## Logging

```ts
import { configure } from "@neon3/sdk/log";
configure("debug");  // or NEON3_LOG_LEVEL=debug env var
```

## Error hierarchy

```
NeonError
├── TransportError     # TCP / timeout (retryable)
├── ProtocolError      # framing / envelope violation
├── RemoteError        # runtime rejected the RPC
├── CapabilityError    # missing required capability
└── ...
```

## Testing

```bash
npm test
```

## Version

- SDK 0.1.6 → runtime v0.2.10
