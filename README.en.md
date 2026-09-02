# Neon3 SDK

<p align="center">
  <a href="README.md">中文</a> ·
  <a href="README.en.md"><strong>English</strong></a>
</p>

<p align="center"><strong>Multi-language client SDKs for Neon3</strong><br />
Start the Runtime, submit UI, handle events, and maintain application state through one public protocol.</p>

<p align="center"><img src="docs/neon3-sdk-intro.png" width="1120" alt="Neon3 SDK and runtime overview" /></p>

> **Install from PyPI or npm.** This GitHub repository presents SDK capabilities, roadmap, and source code. It is not the recommended installation path for normal users.

## Published SDKs

| SDK | Install | Package | Version |
| --- | --- | --- | --- |
| Python | `python -m pip install --upgrade neon3-sdk` | [PyPI: neon3-sdk](https://pypi.org/project/neon3-sdk/) | `0.1.4` |
| Node.js / TypeScript | `npm install @neon3/sdk` | [npm: @neon3/sdk](https://www.npmjs.com/package/@neon3/sdk) | `0.1.4` |

The Python and Node.js SDKs resolve and download the latest [Neon3 Runtime Release](https://github.com/unco999/Neon3-CiJian/releases) by default. Set `NEON3_RUNTIME_VERSION` only when reproducing a specific issue.

```powershell
# Optional: use a local runtime checkout
$env:NEON_ROOT = "D:\Neon3"

# Optional: pin a runtime version
$env:NEON3_RUNTIME_VERSION = "vX.Y.Z"
```

## Language Roadmap

| Client | Status | Package |
| --- | --- | --- |
| Python | Published | [PyPI](https://pypi.org/project/neon3-sdk/) |
| Node.js / TypeScript | Published | [npm](https://www.npmjs.com/package/@neon3/sdk) |
| Rust | In development | crates.io: in development |
| C | In development | C ABI / DLL: in development |
| C++ | In development | C++ SDK / DLL: in development |
| C# / .NET | Planned | NuGet: planned |
| Go | Planned | pkg.go.dev: planned |

## Run Examples

| Example | Language | Link |
| --- | --- | --- |
| Neon3 Inventory Example | Python / Node.js | [Neon3-example](https://github.com/unco999/Neon3-example) |
| Full control gallery | Rust | [component-gallery](https://github.com/unco999/Neon3-CiJian#start-with-examples) |

The inventory example includes window startup, drag and drop, capacity switching, JSONL probes, and test commands. It is the recommended way to verify an SDK installation.

## Repositories

- [Neon3 Runtime](https://github.com/unco999/Neon3-CiJian)
- [Neon3 SDK](https://github.com/unco999/Neon3Sdk)
- [Bevy NUI Plugins](https://github.com/unco999/bevy-nui-plugins)
- [Neon3 Examples](https://github.com/unco999/Neon3-example)

## Contributors

This repository is intended for SDK maintenance, protocol work, and contributions. Source test entry points:

```powershell
Set-Location packages\python-sdk
python -m unittest discover -s tests -v

Set-Location ..\node-sdk
npm test
```

## License

MIT or Apache-2.0.
