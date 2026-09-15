# Neon3 SDK 便携性差距分析（对比 FFmpeg）

> 日期：2026-09-15
> 状态：已确认，待 runtime 侧排期
> 写给：Neon3-CiJian runtime 团队

## 结论

Neon3 SDK 目前的便携性约为 FFmpeg 的 **60%**。差距不在 SDK 封装层（facade API 已做到一行启动），而在**部署模型本身**：runtime 是 3 个独立进程 + TCP loopback RPC，FFmpeg 是单二进制静态库。这是架构选择的 trade-off，不是缺陷，但需要 runtime 侧配合才能缩小。

## 1. 部署模型对比

### FFmpeg 的便携性

```
ffmpeg.exe  ← 单文件，静态链接所有编解码器
```

- 零依赖（除 CRT）
- 不需要先启动守护进程
- C API 直接 link，功能在调用方进程内
- CLI 是一等公民
- 跨平台

### Neon3 现状

```
用户机器
├── neon-eventd.exe        ← 39101，事件总线
├── neon-ui-runtime.exe    ← 39102，UI 逻辑
├── neon-wgpu-runtime.exe ← 39103，GPU 渲染
└── 用户进程（Python/Node/C++/Rust）
     └── SDK 通过 TCP loopback 连上面 3 个
```

SDK 已做的自动化：
- 首次 `start()` 从 GitHub releases 下载 runtime zip
- 自动 spawn 3 个 exe，等 listen
- facade 层一行 `with start():` 启动

但底层仍是多进程 + TCP RPC。

## 2. 逐项差距

| 维度 | FFmpeg | Neon3 现状 | 差距 |
|---|---|---|---|
| 首次启动 | 下载单二进制（~80MB）即用 | 下载 runtime zip（3 exe）+ 语言 SDK 包 | 慢 2-3 倍 |
| 进程模型 | 单进程，功能在库里 | 3 守护进程 + 用户进程 | 多 3 个进程 |
| 调用方式 | 函数调用（同进程） | TCP RPC（跨进程序列化） | 每帧一次 JSON 序列化 |
| 平台 | 跨平台 | Windows 专属（wgpu + DirectComposition） | 平台锁定 |
| 版本耦合 | ffmpeg.exe 即全部 | SDK 版本必须和 runtime 版本对齐 | 双向耦合 |
| CLI | 一等公民 | neon-cli 是调试入口 | 缺用户 CLI |

## 3. 为什么不能直接做成 FFmpeg 那样

这是架构选择，不是偷懒：

1. **GPU 渲染必须独立进程**：wgpu 用 DirectComposition surface，跨进程共享 GPU 纹理需要独立 D3D device。如果 GPU 逻辑跑在用户进程里，Python/Node/C++ 都得 link wgpu——5 个语言绑定就没意义了。
2. **崩溃隔离**：GPU 驱动 crash 不拖垮业务进程。
3. **语言解耦**：Python 不用装 Rust 工具链，Node 不用 link C++ 静态库。

代价就是便携性。FFmpeg 编解码是 CPU 纯计算能静态链接；Neon3 GPU 渲染是系统资源必须独立进程。

## 4. 改进路径（按投入排序）

### 4.1 短期：单 launcher（SDK 侧可做，~1 周）

现在 3 个 exe 分开。做一个 `neon3.exe` 内部 fork 3 个子进程，用户只看到一个进程。SDK `start()` 只 spawn 一个 exe。

**收益**：任务管理器干净，用户不需要知道 3 个进程存在。

### 4.2 中期：in-process 嵌入式模式（需 runtime 侧配合）

让 C/C++/Rust 用户可选把 runtime 静态链接进自己进程，不走 TCP：

```c
neon3_runtime_inproc_start();
neon3_view_set_extras(client, rows);  // 函数调用，无 RPC
```

Python/Node 仍走 TCP（无法 link Rust），但 C++ 游戏引擎可零进程开销。

**需要 runtime 侧做**：把 neon-ui-runtime + neon-wgpu-runtime 编译成静态库，提供 C ABI 的 in-process 入口。

### 4.3 长期：cross-platform surface 共享（需 runtime 侧配合）

现在 surface 共享硬编码 Windows（DirectComposition/DXGI）。wgpu 本身支持 Linux/macOS/Vulkan，但 surface 共享层需要抽象。

**需要 runtime 侧做**：
- Linux：D3D -> Vulkan external memory + DMA-BUF
- macOS：IOSurface
- 抽象 `SurfaceHandle` trait

## 5. Neon3 有 FFmpeg 没有的东西

诚实记录：这不是纯差距，是 trade-off。

- 跨进程共享 GPU 纹理（DirectComposition surface handle）
- GPU→CPU 事件回传（shader.event）
- 声明式 UI flow（NUI）
- 多语言绑定不需要 link wgpu

FFmpeg 是"数据进数据出"；Neon3 是"渲染进程和业务进程分离但共享 GPU 资源"。这两个定位不同，不是谁替代谁。

## 6. SDK 侧已完成的补偿

- facade 层 `start/mount/state/on` 一行启动（Python/Node/Rust）
- 自动下载 runtime + spawn 进程
- constants 枚举层（IDE 智能提示）
- 5 语言统一 wire 契约

---

*本文档由 SDK 侧维护，runtime 侧排期时参考 §4.2/§4.3。*
