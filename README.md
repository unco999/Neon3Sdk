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
| Python | `python -m pip install --upgrade neon3-sdk` | [PyPI: neon3-sdk](https://pypi.org/project/neon3-sdk/) | `0.1.4` |
| Node.js / TypeScript | `npm install @neon3/sdk` | [npm: @neon3/sdk](https://www.npmjs.com/package/@neon3/sdk) | `0.1.4` |

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
| Rust | 开发中 | crates.io：开发中 |
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
