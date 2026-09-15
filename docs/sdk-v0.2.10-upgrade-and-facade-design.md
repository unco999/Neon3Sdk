# Neon3 SDK v0.2.10 升级与 Facade 改造设计

> 状态：草案 · 2026-09-15
> 基线：SDK 0.1.5（wire contract 冻结于 v0.2.x，2026-09-02）
> 目标 runtime：Neon3-CiJian **v0.2.10**（2026-09-15）
> 适用语言：Python（权威参考实现）、Node/TypeScript、Rust、C/C++（对齐）

---

## 0. TL;DR

1. Runtime 从 v0.2.3 走到 v0.2.10，**真正需要 SDK 补的新 wire 只有三块**：
   - `shader.event` 事件（v0.2.7）
   - `wgpu.ui.set_view_extras` RPC（v0.2.7）
   - `wgpu.ui.animation.{pause,resume,seek,cancel}` RPC（v0.2.10）
2. 现有高层 API（`NeonApp` / `ObservableStore` / `RenderClient`）能用但**繁琐**：用户要理解
   revision、input_revision、idempotency_key、ScalarStore/CollectionStore/SelectionStore 三套、
   SurfaceOpen/SurfaceSize/SurfaceKind 一堆 dataclass。
3. 本次改造**不推翻底层**，在 wire/session 之上新增一层 `facade`（门面），用
   `state()` / `on()` / `mount()` 三个函数把 90% 业务代码压到 5 行以内，风格对齐
   React hooks（`useState` / `useEffect` / `on(event, handler)`）。
4. 老 API 全部保留，新 API 渐进采用，0.1.6 同批发布。

---

## 1. 事实层：v0.2.4 → v0.2.10 新增 wire 定义

以下结构全部从 `Neon3-CiJian` v0.2.10 源码（`crates/neon-wgpu-runtime/src/lib.rs`）
逐行核对，不是 release notes 的转述。

### 1.1 `shader.event` 事件（v0.2.7）

- **通道**：eventd（`neon3.event` v1.0），事件名固定 `"shader.event"`，`schema_version = 1`。
- **publisher**：`wgpu-runtime`。
- **payload**（JSON）：

  ```json
  {
    "event_id": 12345678,
    "payload": [0.1, 0.2, 0.3, 0.4]
  }
  ```

  - `event_id`：u32，WGSL 侧 `emit_shader_event(event_id, payload)` 的第一个参数
    （FNV-1a 32-bit hash，由 shader 作者自己算）。
  - `payload`：长度恒为 4 的 f32 数组（vec4）。
- **idempotency_key**：`shader-event:{epoch}:{frame_sequence}:{index}`，SDK 不需要自己生成。
- **触发时机**：每帧渲染后由 wgpu-runtime 读回 GPU→CPU buffer，worker 线程发布，
  不阻塞渲染循环。
- **订阅方式**：现有 `EventClient.subscribe(name="shader.event")` 已经能收到，
  不需要改事件层；缺的只是 typed model。

### 1.2 `wgpu.ui.set_view_extras` RPC（v0.2.7）

- **target**：`wgpu-runtime`
- **method**：`wgpu.ui.set_view_extras`
- **params**：

  ```json
  { "extras": [[f32, f32, f32, f32], ...10 个] }
  ```

  必须恰好 10 个元素，每个元素长度恒为 4。少于/多于 10 个返回
  `invalid_request`。
- **result**：`{"status": "ok", "slots": 10}`
- **shader 侧访问**：`view.extras[0]` … `view.extras[9]`。
- **语义**：进程级全局，下一帧起对所有 surface 生效；不参与 revision 模型，
  不需要 idempotency_key。
- **典型用途**：音频频谱（32 频段拆进 8 个 vec4）、能量值、时间 uniform。

### 1.3 动画控制 RPC（v0.2.10）

四个方法，同一组参数规则：

| method | params | 必填 |
| --- | --- | --- |
| `wgpu.ui.animation.pause`   | `{ "node_path": "<string>" }` | `node_path` + `idempotency_key` |
| `wgpu.ui.animation.resume`  | `{ "node_path": "<string>" }` | 同上 |
| `wgpu.ui.animation.cancel`  | `{ "node_path": "<string>" }` | 同上 |
| `wgpu.ui.animation.seek`    | `{ "node_path": "<string>", "progress": 0.0..=1.0 }` | 同上 + `progress` |

- **target**：`wgpu-runtime`
- **`idempotency_key` 强制**：不传直接 reject（源码 10419 行）。SDK facade 必须自动生成，
  格式建议 `anim:{node_path}:{action}:{uuid7}`。
- **`progress`**：f32，闭区间 [0, 1]，越界返回 `animation_progress_invalid`。
- **错误码**：

  | code | 含义 |
  | --- | --- |
  | `animation_node_required` | 缺 `node_path` |
  | `animation_progress_invalid` | `progress` 非有限数或不在 [0,1] |
  | `window_compositor_unavailable` | 无窗口合成器 |
  | `window_compositor_timeout` | 5 秒内合成器未确认 |
  | `backend_not_available` | headless / 无窗口 GPU |

- **capability**：`wgpu.ui.animation.control.v1`（硬编码字符串）+
  `wgpu.ui.timeline.animation.v1`（`CAPABILITY_TIMELINE_ANIMATION`）。
- **限制**：仅窗口化渲染器可用；headless external surface 走 `backend_not_available`。

### 1.4 `ui.click_blank` 语义事件（v0.2.9）

- 点空白区域（ID map 空）或无 intent 组件时，runtime 经 `ui.host.inbound` 发
  `kind = "semantic_intent"`，其 `event.intent = "ui.click_blank"`，`payload` 为点击坐标
  （vec2）。
- **SDK 现状**：`models.py` 里 `kind` 是自由字符串，代码零改动即可收发；
  wire contract §4.2 的 kind 词表需要补这一项，并加 fixture。
- **用途**：outside-click 关闭 Popup / MenuBar。

### 1.5 新组件（v0.2.9）

Switch / Toast / MenuBar / Accordion / Spinner / Divider / Popup。
NUI 文本透传，**不引入新 RPC**。`capabilities.py` 的 `FLOW_CAPABILITY_REQUIREMENTS`
不需要加映射（这些组件走通用 `ui.fragment.submit.v1`）。

### 1.6 不需要动的部分

- v0.2.4：纯交互 bugfix。
- v0.2.5：Android GPU surface —— SDK 0.1.5 已封装。
- v0.2.6：TextInput typed 文本外发 —— 现有 `text_edit_commit` payload 已兼容，
  补一个 fixture 即可。
- v0.2.9 skin 扩到 27 种：runtime 内部，SDK 不涉及。

---

## 2. 现有 API 痛点诊断

以 Python SDK 0.1.5 为例，一个"计数器"业务要写：

```python
# 老写法（现状，约 18 行样板）
with NeonApp.start(mode="windowed", origin="demo") as app:
    program = app.ui.mount_flow_file("counter.nui")
    state = ObservableStore({"count": 0})
    count_slot = state.scalar("count")
    app.ui.bind("count", count_slot)

    @app.intent("btn.increment")
    def _(event):
        with state.transaction():
            count_slot.set(count_slot.value + 1)

    app.run()
```

痛点：

1. **Store 三件套**：`ObservableStore` / `ScalarStore` / `CollectionStore` /
   `SelectionStore`，用户要知道用哪个、`transaction()` 何时开、`mark_applied` 何时调。
2. **绑定是两步**：先建 store，再 `app.ui.bind(node, store)`，node key 是字符串，
   拼写错误运行时才发现。
3. **revision / input_revision / idempotency_key**：高级用户才能碰，普通用户被
   `stale_revision` 打回来时不知道怎么办。
4. **渲染控制层**：`RenderClient` + `SurfaceOpen` + `SurfaceSize` + `SurfaceKind` +
   `BufferCount` 五个 dataclass，开一个离屏 surface 要 12 行。
5. **事件订阅是阻塞迭代器**：`EventSubscription.recv()` 是同步阻塞，
   没有 `on(event, handler)` 回调模型。
6. **shader event / view_extras / animation control**：零封装。

---

## 3. 设计目标

| 目标 | 验收标准 |
| --- | --- |
| **极简** | 计数器例子从 18 行压到 5 行；离屏 surface 截图压到 3 行 |
| **hooks 风格** | `state(x)` 返回可读可写对象；`on(event)(handler)` 装饰器；副作用自动解绑 |
| **类型安全** | 泛型 `State[T]`；intent / shader event handler 参数有类型；runtime code 映射成异常 |
| **不破坏老代码** | `NeonApp` / `UiClient` / `RenderClient` / `EventClient` 全部保留，老测试不动 |
| **长期可扩展** | 新增一个 RPC 只改 facade 一个文件；新增一类事件只加一个 `on_xxx` |
| **跨语言对齐** | Python 为权威，Node/Rust/C/C++ 按同一名词翻译，函数签名 1:1 |

---

## 4. 新 Facade API 设计

### 4.1 计数器（新写法）

```python
from neon3 import start, mount, state, on, run

with start(mode="windowed", origin="demo") as app:
    mount("counter.nui")
    count = state(0)

    @on("btn.increment")
    def _():
        count.value += 1

    run()
```

对比老写法：18 行 → 6 行。没有 `ObservableStore`、没有 `transaction()`、
没有 `bind()`、没有装饰器里的 `event` 参数（不需要时不出现）。

### 4.2 核心三件套

#### `start(mode=..., origin=..., transport=...) -> App`

- `mode`: `"windowed" | "headless" | "android"`，默认 `"windowed"`。
- 返回 `App` 上下文管理器，退出时自动 shutdown runtime、关 forward、清缓存连接。
- 等价于老 `NeonApp.start(...)`，但不强制用户接触 `NeonApp` 类。

#### `mount(path_or_source) -> Program`

- 接受 `.nui` 文件路径或 NUI 字符串。
- 自动做 capability 校验、flow 静态检查、submit。
- 返回 `Program`，其上挂 `state()` / `on()` / `anim()` / `shader()` 等子命名空间。

#### `state(initial, *, node=None) -> State[T]`

- 类似 React `useState`。
- `node` 省略时按调用顺序自动绑定到当前 flow 的同名 slot；`node="count"` 显式指定。
- `s.value` 读当前值；`s.value = x` 触发一次 `ui.input.frame`，自动维护
  `expected_input_revision` 和 idempotency_key。
- `State[T]` 是泛型，`state(0)` 推断为 `State[int]`，`state(0.0)` 为 `State[float]`。
- 列表/字典直接 `state([])` / `state({"a": 1})`，diff 由底层 store 算。

#### `on(intent) -> decorator`

- 类似 Node.js `EventEmitter.on`。
- `@on("btn.increment")` 注册一个 semantic intent handler。
- handler 签名：
  - 零参：`def _(): ...`（无参数时常用）
  - 一参：`def _(event): ...`，`event` 类型 `IntentEvent`（含 `payload`、`source_node_key`）
  - 两参：`def _(event, state): ...`，`state` 是当前 `App` 的 store 快照
- `@on("ui.click_blank")` 同样支持（v0.2.9 新事件）。
- handler 抛异常 → SDK 返回 `ui_host_response_rejected`，不崩 runtime。
- `with App(...)` 退出时自动解绑，不需要手动 `off()`。

### 4.3 新增能力的门面

#### shader event 订阅

```python
with start(...) as app:
    mount("audio_visualizer.nui")

    @app.shader.on(0x5F3759DF)   # FNV-1a hash of "pulse.splash.complete"
    def _(payload):
        # payload: list[float]，长度恒为 4
        print("splash complete, energy =", payload[0])
```

- `app.shader.on(event_id: int)` 装饰器。
- 底层：`EventClient.subscribe(name="shader.event")`，后台线程按 `event_id` 分发。
- 不需要用户管 eventd 连接、帧读取、epoch。

#### view_extras（高频数据）

```python
app.renderer.view_extras(
    [0.1, 0.2, 0.3, 0.4],   # slot 0
    [0.5, 0.6, 0.7, 0.8],   # slot 1
    # ... 至多 10 个；不足 10 个自动补 [0,0,0,0]
)
```

- 参数个数 1..10，每个长度 4。
- 内部 padding 到 10 组，直接发 `wgpu.ui.set_view_extras`。
- 典型高频调用（每帧）：SDK 内部做 60Hz 节流，避免 RPC 洪泛。

#### 动画控制

```python
app.anim.pause(node_path="hero.timeline")
app.anim.resume(node_path="hero.timeline")
app.anim.seek(node_path="hero.timeline", progress=0.5)
app.anim.cancel(node_path="hero.timeline")
```

- `node_path` 是 NUI 里动画节点的路径字符串。
- 自动生成 idempotency_key。
- headless / 无窗口时抛 `CapabilityError("wgpu.ui.animation.control.v1")`，
  不发 RPC。
- `seek` 的 `progress` 在 [0,1] 外时 SDK 本地拒绝，不发网络请求。

### 4.4 离屏 surface（对比老写法）

老写法：

```python
renderer = RenderClient(client)
surface = renderer.open_surface(SurfaceOpen(
    session_id="demo", surface_id="hello",
    kind=SurfaceKind.SCREEN_UI,
    size=SurfaceSize(1280, 720), buffer_count=2,
))
surface.save_png("out.png")
```

新写法：

```python
png = app.surface.render("hello.nui", size=(1280, 720))
png.save("out.png")
# 或一行：
app.surface.render("hello.nui").save("out.png")
```

- 内部：自动选 surface_id、session_id、buffer_count=2、open → mount_flow →
  capture_png → 返回 `PNG` 对象（有 `.save(path)` / `.bytes` 属性）。
- 需要精细控制时，老 `RenderClient` 仍然可用：`app.renderer` 就是老对象。

### 4.5 完整示例（音频可视化，串起所有新能力）

```python
from neon3 import start, mount, state, on

with start(mode="windowed") as app:
    mount("audio.nui")
    playing = state(False)

    @on("play.click")
    def _():
        playing.value = True

    @app.shader.on(0xAUDIO_READY)
    def _(payload):
        # shader 每 100ms 发一次当前 RMS
        app.renderer.view_extras(
            [payload[0], 0, 0, 0],   # slot 0 = 当前能量
            [0.0, 0.0, 0.0, 0.0],    # slot 1..9 补零
        )

    @on("seek.bar")
    def _(event):
        app.anim.seek("hero.timeline", progress=event.payload.value)

    app.run()
```

---

## 5. 分层架构

```
┌─────────────────────────────────────────────────┐
│  Facade（新，Python: neon3/facade.py）          │
│  start / mount / state / on / app.shader /     │
│  app.renderer.view_extras / app.anim /          │
│  app.surface.render                             │
├─────────────────────────────────────────────────┤
│  Session（保留）                                 │
│  UiSession: revision/input_revision 自动管理     │
│  IntentRouter / ObservableStore                  │
├─────────────────────────────────────────────────┤
│  Render/Event（保留 + 补 typed wrapper）         │
│  RenderClient: + set_view_extras / animation_*  │
│  EventClient: + ShaderEvent model                │
├─────────────────────────────────────────────────┤
│  Wire（冻结，不改）                              │
│  framing / envelope / error code / fixture digest│
└─────────────────────────────────────────────────┘
```

**规则**：

- Facade 只做"参数推断 + 默认值 + 类型包装"，不重新发明协议字段。
- 新增 RPC 时：wire 不动（如果是新 method），session 层补一个薄方法，
  facade 暴露为 `app.<domain>.<verb>(...)`。
- 新增事件时：facade 加一个 `@app.<domain>.on(...)`，底层 `EventClient` 复用。
- 老代码里所有 `NeonClient.call(target, method, params)` 的裸调用继续合法。

---

## 6. 长期可扩展性规则

1. **新 RPC 进入流程**（以未来 `wgpu.ui.foo` 为例）：
   1. wire contract §4 加一节，写清 target / method / params / result / error code。
   2. `render.py` 或 `ui.py` 加一个薄方法（5 行以内）。
   3. `facade.py` 暴露为 `app.<domain>.<verb>(...)`，带参数默认值和校验。
   4. 跨语言：Node/Rust/C 各加一个对应方法，fixture digest 表更新。
2. **新事件进入流程**：
   1. eventd 侧事件名固定后，facade 加 `@app.<domain>.on(...)`。
   2. 不要求用户知道事件名，domain 方法自带过滤。
3. **capability 演进**：
   - `capabilities.py` 的硬编码列表只放"facade 用到的 capability"。
   - runtime describe 返回新 capability 时，facade 不需要改代码，
     `CapabilitySet.has(...)` 自动生效；只是 facade 的 `.on_xxx()` 会在调用时
     抛 `CapabilityError`。
4. **破坏性变更**：
   - Facade 层语义变更 = minor 版本（0.1.6 → 0.2.0）。
   - Wire 层变更必须走 `docs/sdk-wire-contract.md` 的 `source_runtime` bump
     + fixture digest 表更新，不允许私下改。

---

## 7. 迁移路径

| 用户群体 | 动作 |
| --- | --- |
| 老用户（已用 `NeonApp`） | 不动，0.1.6 保持兼容；新能力按需 `from neon3.facade import ...` |
| 新用户 | 直接 `from neon3 import start, mount, state, on` |
| 内部 example | 背包案例改成新写法作为宣传样例；老 example 保留作高级参考 |
| 跨语言 | Node 先对齐（生态最像 React），Rust/C/C++ 0.1.7 跟上 |

---

## 8. 0.1.6 交付清单

### 8.1 wire 层（不改，只补文档）

- [ ] `docs/sdk-wire-contract.md` `source_runtime` bump 到 v0.2.10
- [ ] §4.2 kind 词表加 `click_blank`
- [ ] §4 加三节：`wgpu.ui.set_view_extras` / `shader.event` / `wgpu.ui.animation.*`
- [ ] `docs/fixtures/wire/` 新增 3 份 fixture：
  - `set-view-extras.json`（10 组 vec4）
  - `shader-event.json`（payload = {event_id, payload[4]}）
  - `animation-seek.json`（node_path + progress）

### 8.2 现有层补薄封装

- [ ] `render.py::RenderClient.set_view_extras(extras: list[list[float]])`
- [ ] `render.py::RenderClient.animation_pause/resume/seek/cancel(node_path, progress=None)`
- [ ] `event.py` 加 `ShaderEvent` dataclass（`event_id: int`, `payload: tuple[float, ...]`）
  和 `EventSubscription.shader_events()` 生成器
- [ ] `capabilities.py` 加：
  - `wgpu.ui.animation.control.v1`
  - `wgpu.ui.timeline.animation.v1`
- [ ] `models.py` semantic intent kind 词表（如果有枚举）加 `click_blank`

### 8.3 Facade 新层（Python 先行）

- [ ] `neon3/facade.py`：`start` / `mount` / `state` / `on`
- [ ] `neon3/facade/renderer.py`：`view_extras(...)` + 60Hz 节流
- [ ] `neon3/facade/animation.py`：`pause/resume/seek/cancel`
- [ ] `neon3/facade/shader.py`：`on(event_id)`
- [ ] `neon3/facade/surface.py`：`render(nui, size=...) -> PNG`
- [ ] `__init__.py` 导出 `start / mount / state / on / run`
- [ ] 计数器 + 音频可视化两个 example 改成新写法

### 8.4 测试

- [ ] facade 层单元测试：state.set 触发一次 ui.input.frame（mock NeonClient）
- [ ] facade 层单元测试：`on()` handler 在 App 退出后不再被调用
- [ ] 跨语言：Python / Node 对新 3 份 fixture 的 canonical JSON digest 一致
- [ ] 真机 smoke：v0.2.10 runtime 上跑通
  - set_view_extras → shader 读回非零
  - shader.event 收到非零 payload
  - animation.pause/resume/seek 各一次，不返回 backend_not_available

---

## 9. 五语言并行更新矩阵

### 9.1 架构层级（决定工作量分布）

勘察 5 个 SDK 源码后的事实：

```
独立实现（各自有 wire/session/render/event，逻辑写三遍）
├── Python  (packages/python-sdk)
├── Node/TS (packages/node-sdk)
└── Rust     (packages/rust-sdk)   ← C/C++ 的事实后端

薄包装（机械翻译，逻辑零重复）
├── C    (packages/c-sdk)  ← cdylib over Rust core，现有 ABI 仅 9 个函数
└── C++  (packages/cpp-sdk) ← header-only RAII over C ABI
```

**关键事实**：C SDK 现有 ABI 只有
`client_new/free/call/health/shutdown` + `ui_mount_flow` + `surface_open/save_png` +
`free_string`，**完全没有 eventd 订阅能力**。要在 C 里收 `shader.event`，
必须先补一组事件订阅 ABI（连接、订阅、收帧、回调）。

### 9.2 每个语言要加什么

| 新能力 | Python | Node/TS | Rust | C | C++ |
| --- | --- | --- | --- | --- | --- |
| `set_view_extras(extras)` | `RenderClient` 加方法 | `RenderClient` 加方法 | `RenderClient` 加方法 | `neon3_view_set_extras(float[10][4])` | `client.viewExtras(...)` inline |
| `animation.pause/resume/seek/cancel` | 4 个方法 | 4 个方法 | 4 个方法 | 4 个 `neon3_animation_*` 函数 | 4 个 `client.anim*` inline |
| `shader.event` typed model | `ShaderEvent` dataclass | `ShaderEvent` interface | `ShaderEvent` struct | **事件订阅 ABI（新工作量）** | wrapper over C callback |
| `click_blank` | 词表文档 | 词表文档 | 词表文档 | — | — |
| Facade hooks 风格（state/on/start/mount） | ✅ 写 | ✅ 写（TS 最像 React） | builder 模式 `App::new().mount(..).state(..).on(..)` | ❌ 不做 | ❌ 不做 |
| 离屏 surface 一行截图 | `app.surface.render(...)` | `app.surface.render(...)` | `app.surface.render(...)` | 不做（C 维持原 open/save） | 不做 |

### 9.3 C SDK 要补的事件订阅 ABI（隐藏工作量）

现有 C ABI 没有 eventd 连接，shader.event 在 C 里没法收。新增 4 个函数：

```c
/* 连接 eventd 并按 name 订阅，返回 opaque 订阅句柄 */
NEON3_API int neon3_event_subscribe(neon3_client* client,
                                    const char* name,
                                    neon3_event_subscription** out_sub,
                                    char** out_error);

/* 阻塞读一帧，payload 是 {event_id, payload[4]} 的 JSON 字符串 */
NEON3_API int neon3_event_recv(neon3_event_subscription* sub,
                               uint64_t timeout_ms,
                               char** out_payload_json,
                               char** out_error);

/* 注册 shader.event 回调（每收到一个 event_id 触发一次） */
typedef void (*neon3_shader_event_fn)(uint32_t event_id,
                                      const float payload[4],
                                      void* user_data);
NEON3_API int neon3_shader_listen(neon3_event_subscription* sub,
                                  neon3_shader_event_fn cb,
                                  void* user_data);

NEON3_API void neon3_event_subscription_free(neon3_event_subscription* sub);
```

Rust 侧（`c-sdk/src/lib.rs`）实现这 4 个函数，C++ 侧包成
`neon3::EventSubscription` 类。

### 9.4 Facade 在各语言的形态

| 语言 | Facade 形态 | 例子 |
| --- | --- | --- |
| Python | hooks 风格函数 | `with start(): mount(); c = state(0); @on(...)` |
| Node/TS | 同 Python，Promise + 装饰器 | `await start(); mount(); const c = state(0); on(...)` |
| Rust | builder 模式（无闭包装饰器习惯） | `App::start()?.mount("x.nui")?.state("count", 0)?.on("btn", h)?.run()?;` |
| C | 不做 facade，暴露原语 | 用户直接调 `neon3_view_set_extras(...)` |
| C++ | 轻量 RAII，不做 hooks | `auto app = App::windowed(); app.mount("x.nui");` |

### 9.5 推进顺序（不是 5 倍工作量）

1. **Rust 先做**（0.1.6-alpha.1）：wire 层补 3 个新方法 + 事件订阅
   ABI。这是 C/C++ 的事实后端。
2. **Python / Node 并行**（0.1.6-alpha.2）：按 Rust 的 wire 实现补
   typed 方法 + facade hooks 层。
3. **C/C++ 机械翻译**（0.1.6-alpha.3）：Rust 的 cdylib 加新符号，
   `neon3.h` / `neon3.hpp` 各加对应函数。
4. **跨语言 fixture digest 校验**：3 份新 fixture 在 Py/TS/Rust 三处
   canonical JSON sha256 一致。
5. **真机 smoke**：v0.2.10 runtime 上 5 个语言各跑一遍
   set_view_extras / shader.event / animation.seek。

### 9.6 工作量估算

| 语言 | 新增代码 | 备注 |
| --- | --- | --- |
| Rust | ~350 行（render +120, session +80, event +150） | C/C++ 的源 |
| Python | ~400 行（render +60, event +80, facade +260） | facade 大头 |
| Node | ~400 行（同 Python） | facade 大头 |
| C | ~180 行（neon3.h + 30, lib.rs + 150） | 事件订阅是新工作量 |
| C++ | ~80 行（neon3.hpp 加 inline wrapper） | 纯翻译 |
| 文档/fixture | ~150 行 | wire contract + 3 fixture |

合计约 1500 行，按"Rust → Py/TS → C/C++"顺序推，不是 5 倍并行。

---

## 10. 风险与未决

1. **事件线程模型**：`shader.event` 订阅需要后台线程读 eventd。Python GIL 下 handler
   执行顺序要在文档里写清楚（handler 由 SDK 内部锁串行调用，不保证实时性）。
2. **`state()` 自动绑定 node key**：按调用顺序绑定在多个 flow 之间可能串。
   规则：`state(...)` 必须在 `mount()` 之后调用；同一 flow 内按调用顺序对应
   slot 顺序。文档里用例子讲清楚，不做强类型反射。
3. **view_extras 节流**：60Hz 是建议值，做成可配置
   `app.renderer.view_extras(..., throttle_hz=60)`。
4. **headless 限制**：动画控制仅窗口化可用，facade 在 headless 下调用要在
   `CapabilityError` message 里明确说"windowed renderer required"。
5. **Rust/C/C++ 跟进**：这三个语言没有 Python 的装饰器习惯，facade 在那边
   翻译成 builder 模式（`App::new().mount(...).state(...).on(...).run()`），
   名词不变。
