# neon3-sdk

Python client SDK for Neon3 `neon3.rpc` and `neon3.event`.

## Install

```powershell
python -m pip install --upgrade neon3-sdk
```

Package page: https://pypi.org/project/neon3-sdk/

## Start Neon3

`RuntimeSession` starts the Neon3 services as separate processes. On Windows it
resolves and downloads the latest runtime release from:

https://github.com/unco999/Neon3-CiJian/releases

```python
from neon3_sdk import RuntimeConfig, RuntimeMode, RuntimeSession

with RuntimeSession(RuntimeConfig(mode=RuntimeMode.WINDOWED)):
    print("Neon3 services are running")
```

The resolved release is cached under `%LOCALAPPDATA%\Neon3Sdk\runtime\<tag>`.
Set `NEON3_RUNTIME_VERSION=<tag>` (for example `v0.2.3`) when reproducible
pinning is required; only pin a runtime that is at least as new as the UI
schema your flows use, otherwise newer nodes such as `tooltip` or `canvas`
fail with `nui_flow_unknown_attribute`.
Set `NEON_ROOT` or pass `RuntimeConfig(neon_root="D:/Neon3", profile="debug")`
to use a local checkout. The SDK starts `neon-eventd`, `neon-wgpu-runtime`, and
`neon-ui-runtime`; it does not create windows or GPU resources itself.

## RPC Usage

```python
from neon3_sdk import NeonClient, UiClient

rpc = NeonClient.connect("127.0.0.1:39102", origin="my-tool")
ui = UiClient(rpc)
program = ui.submit_flow('version 1\nsurface example revision 1\nsurface root\n')
print(program.surface_id)
```

## Event Usage

```python
from neon3_sdk import EventClient

with EventClient.connect("127.0.0.1:39101").subscribe(
    name="ui.file_drop.accepted"
) as events:
    for image in events.file_drops():
        print(image.file_name, image.source_path)
```

`ui.file_drop.accepted` is the existing Neon3 event bridge for OS file drops.
Image tools can use it to start OpenCV analysis without polling.

## Tests

```powershell
python -m unittest discover -s tests -v
```
