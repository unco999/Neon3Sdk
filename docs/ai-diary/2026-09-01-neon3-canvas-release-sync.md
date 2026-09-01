---
date: 2026-09-01
topic: Neon3 Canvas 更新后的 SDK 与 Bevy 发布同步方案
type: implementation
status: completed
---

## 涉及的 crate / 文件路径

- `D:/Neon3`：Canvas V1、UI Runtime、WGPU renderer 与真实窗口 probe
- `D:/Neon3Sdk/scripts/sync-neon3-stack.ps1`
- `D:/Neon3Sdk/scripts/build-neon3-release.ps1`
- `D:/Neon3Sdk/README.md`
- `D:/Neon3Sdk/packages/python-sdk`
- `D:/Neon3Sdk/packages/node-sdk`
- `D:/bevy-nui-plugins`

## 发现的问题

- Neon3 的 Canvas 更新位于 schema / UI Runtime / WGPU renderer，当前未改变 `neon3.rpc` 公共协议版本或 SDK client API。
- `D:/Neon3` 本地 `master` 为 `faf74ea`，相对 `origin/master` ahead 4，尚未推送；SDK 当前固定下载 `v0.2.1` release，因此新 Canvas 不会进入已发布 SDK runtime。
- `bevy-nui-plugins` 当前干净、依赖 crates.io Neon3 `0.2.0`，没有直接使用 Neon3 checkout；本次不需要改插件源码。

## 采取的方案

- 新增 `scripts/sync-neon3-stack.ps1`：依次运行真实 `canvas_window_probe`、Neon3 workspace check、Python tests、Node tests、Bevy check，并输出 JSONL 与 JSON manifest。
- Pipeline 先显式构建 `neon-ui-runtime`、`canvas_window_probe` 及其 WGPU 兄弟进程，避免清理 target 后 probe 因找不到 sibling executable 而产生假失败。
- 扩展 runtime builder 支持 `-SourceRoot`，使 bundle 可从已验证的本地 Neon3 HEAD 构建，而非只能重新 clone。
- Pipeline 在 `-BuildRuntime` 时强制检查：Neon3 工作区干净、release ref 指向被验证 HEAD、HEAD 已不再 ahead upstream、Python/Node SDK 的 runtime pin 与 release tag 一致。
- 脚本不自动 commit、push、tag、cargo publish、npm publish 或 PyPI publish。

## 当前状态

已完成。Canvas 运行时无需 SDK / Bevy API 代码变更；等待 Neon3 提交推送并创建新 release 后，再更新 SDK 两处 runtime pin 并构建发布包。

## 未完成事项与下一步

1. 在 Neon3 提交并推送后创建例如 `v0.2.2` tag/release。
2. SDK Python 与 Node 的 `NEON3_RUNTIME_VERSION` 同步改为 `v0.2.2`，各自提升包版本并发布。
3. 用 `sync-neon3-stack.ps1 -ReleaseRef v0.2.2 -BuildRuntime` 构建并验证 runtime bundle，再执行人工批准的 GitHub/crates.io/npm/PyPI 发布步骤。

## 测试与验证结果

- `cargo test -p neon-ui-schema canvas -- --nocapture`：2 passed。
- `cargo test -p neon-ui-runtime nui_flow::tests::canvas -- --nocapture`：2 passed。
- `cargo run -p neon-ui-runtime --bin canvas_window_probe`：passed；真实窗口 capture，`frame_sequence=1`、`composition_revision=2`、`red_pixels=208`、`cyan_pixels=1694`。
- Python SDK：9 tests passed。
- Node SDK：2 tests passed，TypeScript build passed。
- Bevy plugin：`cargo check` passed；仅有既有 dead-code warnings。
- 新 pipeline 验证模式：exit 0，6 steps passed，manifest `C:/Users/10540/AppData/Local/Temp/neon3-stack-validation.json`。
- 警告：Neon3 workspace 有既有 unused/dead-code warnings；不作为失败处理。
