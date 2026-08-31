# neon3-sdk

Python SDK for the Neon3 `neon3.rpc` control plane.

```bash
cd packages/python-sdk
pip install -e .
python -m neon3_sdk calculator
```

Tests and deterministic scenario:

```bash
python -m unittest discover -s tests -v
python -m neon3_sdk calculator --once
```

### Event subscriptions

The SDK also exposes the canonical `neon3.event` stream. A WGPU window owner
publishes `ui.file_drop.accepted` for OS file drops; same-machine tools can
subscribe without implementing a second transport:

```python
from neon3_sdk import EventClient

events = EventClient.connect("127.0.0.1:39101").subscribe(
    name="ui.file_drop.accepted"
)
with events:
    for image in events.file_drops():
        print(image.source_path)
```

When `--neon-root` is omitted, the command uses the SDK-local `release`
directory. Set `NEON_ROOT` or pass `--neon-root <path>` only to override it.
Runtime clients can select a checkout profile with `RuntimeConfig(profile="debug")`
or `RuntimeConfig(profile="release")`; `auto` preserves the release-first default.
