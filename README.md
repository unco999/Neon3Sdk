# Neon3 SDK

<p align="center">
  <a href="README.md"><strong>中文</strong></a> ·
  <a href="README.en.md">English</a>
</p>

<p align="center"><strong>Neon3 的多语言客户端 SDK</strong><br />
通过统一公共协议启动 Runtime、提交 UI、处理事件与维护应用状态。</p>

<p align="center"><img src="docs/neon3-sdk-intro.png" width="1120" alt="Neon3 SDK 与 Runtime 总览" /></p>

> **请从 PyPI 或 npm 安装。** 此 GitHub 仓库用于展示 SDK 能力、路线图和源码；普通使用者不建议从此处下载或安装源码。

## 已发布

| SDK | 安装 | 包地址 | 版本 |
| --- | --- | --- | --- |
| Python | `python -m pip install --upgrade neon3-sdk` | [PyPI: neon3-sdk](https://pypi.org/project/neon3-sdk/) | `0.1.5` |
| Node.js / TypeScript | `npm install @neon3/sdk` | [npm: @neon3/sdk](https://www.npmjs.com/package/@neon3/sdk) | `0.1.5` |
| Rust | `cargo add neon3-sdk` | [crates.io: neon3-sdk](https://crates.io/crates/neon3-sdk) | `0.1.0` |
| C | 链接 `neon3_c`（DLL/静态库） | [GitHub Release v0.1.0](https://github.com/unco999/Neon3Sdk/releases/tag/v0.1.0) | `0.1.0` |
| C++ | 链接 `neon3_c` + `#include <neon3.hpp>` | [GitHub Release v0.1.0](https://github.com/unco999/Neon3Sdk/releases/tag/v0.1.0) | `0.1.0` |

Python 与 Node.js SDK 默认解析并下载 [Neon3 Runtime Releases](https://github.com/unco999/Neon3-CiJian/releases) 的最新版本。只有复现问题时才设置 `NEON3_RUNTIME_VERSION`。

```powershell
# 可选：使用本地 runtime checkout
$env:NEON_ROOT = "D:\Neon3"

# 可选：固定 runtime 版本
$env:NEON3_RUNTIME_VERSION = "vX.Y.Z"
```

## 语言路线图

| 客户端 | 发布状态 | 包地址 |
| --- | --- | --- |
| Python | 已发布 | [PyPI](https://pypi.org/project/neon3-sdk/) |
| Node.js / TypeScript | 已发布 | [npm](https://www.npmjs.com/package/@neon3/sdk) |
| Rust | 已发布 | [crates.io](https://crates.io/crates/neon3-sdk) |
| C | 已发布 | [GitHub Release v0.1.0](https://github.com/unco999/Neon3Sdk/releases/tag/v0.1.0) · `neon3.h` |
| C++ | 已发布 | [GitHub Release v0.1.0](https://github.com/unco999/Neon3Sdk/releases/tag/v0.1.0) · `neon3.hpp` |
| C | 开发中 | C ABI / DLL：开发中 |
| C++ | 开发中 | C++ SDK / DLL：开发中 |
| C# / .NET | 规划中 | NuGet：规划中 |
| Go | 规划中 | pkg.go.dev：规划中 |

## 运行案例

| 案例 | 适用语言 | 链接 |
| --- | --- | --- |
| Neon3 背包案例 | Python / Node.js | [Neon3-example](https://github.com/unco999/Neon3-example) |
| 完整控件案例 | Rust | [component-gallery](https://github.com/unco999/Neon3-CiJian#从案例开始) |

背包案例包含窗口启动、拖拽、容量切换、JSONL probe 和测试命令，是验证 SDK 安装的推荐入口。

## Android 能力

Neon3 SDK 可以直接连接 Android 设备上运行的 Neon3 Host（APK 内的
`Neon3HostService`，后台前台服务、无窗口、无黑屏）。Host 在
`127.0.0.1:43100` 暴露同一个 `neon3.rpc/1` 端点，SDK 通过 adb forward
连接后，与桌面使用完全相同的协议（`ui.*`、`wgpu.*`、`render.*`、
`service.*`），无需在 Android 上安装额外运行时。

```python
from neon3_sdk import NeonApp

app = NeonApp.start(transport="android")          # 自动 adb 发现 + forward
app.ui.mount_flow_file("hello.nui")
app.stop()
```

```ts
import { NeonApp } from "@neon3/sdk";

const app = await NeonApp.start({ transport: "android" });  // 自动 adb 发现 + forward
await app.ui.mountFlowFile("hello.nui");
await app.stop();
```

也可以手动建立连接：

```python
from neon3_sdk import AndroidSession, AndroidConfig, NeonClient

session = AndroidSession(AndroidConfig())          # 可指定 device / adb / host
handle = session.start()                            # adb forward + health wait
client = NeonClient.connect(handle.endpoint, allow_non_loopback=True)
# ... 之后与桌面完全一致 ...
session.stop()                                      # service.shutdown + 清理 forward
```

## 共享表面纹理申请与图片测试

SDK 可以在不启动窗口的情况下申请跨进程共享表面纹理（Windows 为 D3D12 共享
纹理，Android 为 Vulkan/离屏 wgpu 纹理），并把最新帧保存为 PNG 用于自动化
验收。

### 申请表面纹理

```python
from neon3_sdk import RenderClient, SurfaceOpen, SurfaceSize, SurfaceKind

renderer = RenderClient(client)                # client = NeonClient 实例
surface = renderer.open_surface(SurfaceOpen(
    session_id="demo",
    surface_id="hello",
    kind=SurfaceKind.SCREEN_UI,
    size=SurfaceSize(width=1280, height=720),
    buffer_count=2,
))
```

```ts
import { RenderClient } from "@neon3/sdk";

const renderer = new RenderClient(client);      // client = NeonClient 实例
const surface = await renderer.openSurface({
  sessionId: "demo",
  surfaceId: "hello",
  kind: "screen_ui",
  width: 1280,
  height: 720,
  bufferCount: 2,
});
```

注意：申请尺寸与渲染逻辑尺寸（默认 1280x720）越接近，画面缩放越小。若使用
很小的表面（如 320x200），UI 会被等比缩小。

### 保存图片（PNG 测试）

```python
surface.save_png("captures/surface.png")        # Python
await surface.savePng("captures/surface.png")   # Node.js
```

`render.surface.capture_png` 由 `neon-wgpu-runtime` 读回共享表面并写出 PNG，
原生 GPU 句柄不会进入 JSON。自动验收可对产物做签名断言：

```python
import pathlib
png = pathlib.Path("captures/surface.png").read_bytes()
assert png[:8] == b"PNG


"          # 有效 PNG
```

在 Windows 上这一步同时验证 D3D12 共享纹理的 readback 链路；在 Android 上
验证 Vulkan/离屏纹理的 readback 链路。没有 GPU 导出路径的 Host 返回稳定
错误码 `backend_not_available`，而不是 `unsupported_method`。

## 相关仓库

- [Neon3 Runtime](https://github.com/unco999/Neon3-CiJian)
- [Neon3 SDK](https://github.com/unco999/Neon3Sdk)
- [Bevy NUI Plugins](https://github.com/unco999/bevy-nui-plugins)
- [Neon3 Examples](https://github.com/unco999/Neon3-example)

## 开发者

本仓库仅面向 SDK 维护、协议开发和贡献。源码测试入口：

```powershell
Set-Location packages\python-sdk
python -m unittest discover -s tests -v

Set-Location ..\node-sdk
npm test
```

## 许可证

MIT 或 Apache-2.0。
