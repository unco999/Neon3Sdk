# Neon3 Python SDK

Python client SDK for the Neon3 control-plane protocol. Talks the same
`neon3.rpc` wire contract as the Rust and Node SDKs over loopback TCP.

## Install

```bash
pip install neon3-sdk
```

Or from source:

```bash
cd packages/python-sdk
pip install -e .
```

## Quick start (facade, recommended)

```python
from neon3_sdk import start, mount, state, on

with start(mode="windowed", origin="demo"):
    mount("counter.nui")
    count = state(0)

    @on("btn.increment")
    def _():
        count.value += 1

    run()
```

### Renderer features

```python
with start() as app:
    mount("audio.nui")

    # Shader events (GPU -> CPU)
    @app.shader.on(0x5F3759DF)
    def _(payload):
        print("energy:", payload[0])

    # View extras (60 Hz throttled)
    app.renderer.view_extras([0.1, 0.2, 0.3, 0.4])

    # Animation control
    app.anim.seek("hero.timeline", progress=0.5)

    # Offscreen screenshot
    png = app.surface.render("hello.nui", size=(1280, 720))
    png.save("out.png")
```

## Low-level API

```python
from neon3_sdk import NeonClient, RenderClient, UiSession

client = NeonClient.connect("127.0.0.1:39102", origin="demo")
session = UiSession(client)
program = session.mount_flow(open("hello.nui").read())

render = RenderClient(NeonClient.connect("127.0.0.1:39103", origin="demo"))
render.set_view_extras([[0.1, 0.2, 0.3, 0.4]])
render.animation_pause("hero.timeline")
```

## Constants & enums

```python
from neon3_sdk import service, method, AnimationAction

client.call(service.WGPU_RUNTIME, method.WGPU_UI_SET_VIEW_EXTRAS, {...})
client.call(service.WGPU_RUNTIME, AnimationAction.PAUSE.method(), {...})
```

## Logging

```python
from neon3_sdk.log import configure
configure("debug")  # or NEON3_LOG_LEVEL=debug env var
```

## Error hierarchy

```
NeonError
├── TransportError       # TCP / timeout (retryable)
├── ProtocolError        # framing / envelope violation
├── RemoteError          # runtime rejected the RPC
├── CapabilityError      # missing required capability
├── StaleRevisionError   # revision mismatch (retryable)
└── ...
```

## Testing

```bash
python -m unittest discover -s tests
```

## Version

- SDK 0.1.6 → runtime v0.2.10
- See `CHANGELOG.md` for the full compatibility matrix.
