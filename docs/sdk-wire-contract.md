---
title: Neon3 SDK 跨语言 wire 契约（Stage 000 冻结）
date: 2026-09-02
status: frozen
source_runtime: Neon3-CiJian v0.2.x (commit observed 2026-09-02, cached source under .cache/neon3/source)
---

# Neon3 SDK 跨语言 wire 契约

> 本文件是 `D:\Neon3Sdk` 下 Python SDK 与 Node SDK 的 wire 层唯一真源。
> 任何高级 API（Stage 001 之后）不得重新发明协议字段；所有字段以 runtime
> `neon-protocol` / `neon-ui-schema` crate 的 serde 定义为权威，wire 一律
> snake_case。canonical JSON fixture 位于 `docs/fixtures/wire/`，两套 SDK 的
> 契约测试必须解析同一组文件并产出字节一致的规范化输出。

## 1. 传输层

### 1.1 长度前缀 framing

- 每个请求 / 响应 / 事件帧为：4 字节大端无符号长度 + UTF-8 JSON 对象。
- 请求模型为一连接一请求（`neon3.rpc`）；事件订阅为长连接多帧。
- 帧大小上限：RPC 请求与响应 `128 * 1024 * 1024` 字节；事件层单帧
  `64 * 1024` 字节。超限时 SDK 必须以 `TransportError("frame_too_large")`
  拒绝，不得截断。

### 1.2 RPC 请求信封（`neon3.rpc` v1.0）

```json
{
  "protocol": "neon3.rpc",
  "version": {"major": 1, "minor": 0},
  "request_id": "<uuid>",
  "client": {"kind": "cli", "instance_id": "<uuid>", "pid": 0, "origin": "<string>"},
  "target": "<service name>",
  "method": "<method>",
  "params": {},
  "expected_revision": null,
  "idempotency_key": null
}
```

- `client.kind`：CLI / 探针使用 `"cli"`，领域宿主使用 `"external_host"`。
- `expected_revision` 与 `idempotency_key` 可为 `null`，字段必须存在。

### 1.3 RPC 响应信封

字段集合固定为六个，多余字段或缺字段均判 `ProtocolError`：

```json
{
  "request_id": "<必须回显请求 request_id>",
  "status": "accepted | rejected | failed",
  "revision": "integer | null",
  "result": "value | null",
  "snapshot": "value | null",
  "error": "object | null"
}
```

- `status != "accepted"` 时 `error.code`（字符串）与 `error.message`（字符串）
  为约定必备键；SDK 公共错误类型必须可读取 `code` / `message`，`details` 与
  `retryable` 为 Stage 002 起的 SDK 侧规范化字段（runtime 暂不返回时由 SDK
  依据 code 推导，见 §6）。
- 响应 `request_id` 与请求不一致时必须判 `ProtocolError`，禁止交付业务层。

### 1.4 事件信封（`neon3.event` v1.0）

订阅握手：客户端发送 `{kind:"subscribe", protocol, version, request_id,
client, filters[], replay_from_sequence, max_rate_hz}`；服务端以
`{kind:"ack", status:"accepted"|...}` 应答。此后每个投递帧为
`{kind:"delivery", event: EventEnvelope}`。

`EventEnvelope` 字段：`protocol, version{major,minor}, event_id, name,
schema_version, epoch, sequence, timestamp_unix_ms, publisher(ClientIdentity),
payload`。事件层不承载 revision 语义，UI 状态同步一律走 RPC。

### 1.5 服务地址（默认 `RuntimeConfig`）

| 服务 | 默认端点 | 说明 |
| --- | --- | --- |
| `eventd` | `127.0.0.1:39101` | 事件总线 |
| `ui-runtime` | `127.0.0.1:39102` | UI 程序 / 宿主入站 |
| `wgpu-runtime` | `127.0.0.1:39103` | 渲染器 |
| domain（示例） | `127.0.0.1:39104` | 业务 RPC server 绑定口 |

端点必须是 loopback；SDK 构造时解析并校验 host 与端口范围。

## 2. 通用基础类型

| 类型 | wire 形态 | 备注 |
| --- | --- | --- |
| `Revision` | 非负整数 | 透明 u64 |
| `ServiceName` | 字符串 | 透明 |
| `UiProgramRevision` | `{program_id, revision, schema_version, capabilities[]}` | capabilities 条目为 `{name, version, owner, status}`，`owner ∈ {ui_runtime, wgpu_runtime, shared_contract}`，`status ∈ {experimental, supported, deprecated}` |
| `UiTextHandle` | `{id: u64, generation: u32}` | 文本注册表句柄，不得跨 epoch 复用 |
| `UiFragmentRevision` | `{id: string, revision}` | |
| `UiSemanticInteractionMetadata` | `{interaction_id, sequence, renderer_epoch}` | |

### 2.1 `UiInputValue` / `UiSemanticPayloadValue` 的可判别联合

tag 字段固定为 `"kind"`（snake_case 变体名），载荷键为 `value`（
`AssetHandle` 例外，为 `{kind:"asset_handle", id, generation}`）：

```text
bool | i32 | u32 | f32 | vec2 | vec4 | color | enum | text_handle | asset_handle | canvas_data
```

- canonical fixture 中只允许整数值的 f32（如 `1.0` 写作 `1`），避免不同
  JSON 序列化的浮点字面量差异；契约测试断言规范化字节串，含非整数值浮点的
  数据必须在 fixture 中规避。
- 语义事件 payload 只接受 `bool / i32 / u32 / f32 / enum / text_handle /
  asset_handle`（有限词表），不接受任意 JSON、原始坐标或渲染器本地 ID。

## 3. canonical fixture 清单

目录：`docs/fixtures/wire/`。加载路径解析顺序：环境变量
`NEON3_WIRE_FIXTURES` 优先，否则从测试文件位置向上寻找
`docs/fixtures/wire`（仓库根）。

| 文件 | 语义 |
| --- | --- |
| `flow-submit-result.json` | `ui.flow.submit` 的 `result`（surface_id / program_revision / input_schema） |
| `inbound-semantic-intent.json` | `ui.host.inbound` 参数：`{kind:"semantic_intent", event}` |
| `inbound-drag-drop.json` | `ui.host.inbound` 参数：`{kind:"drag_drop", event, active_fragment}` |
| `input-frame.json` | `ui.input.frame` 参数（`UiInputFrame`） |
| `publication.json` | `UiHostPublication`（scalar_frame + grid_inputs + presentation_update） |
| `program-input-snapshot.json` | `debug.ui.host.snapshot` 的 result（`UiProgramInputSnapshot`） |
| `debug-snapshot.json` | `debug.snapshot.get` 的 result（`DebugSnapshot`） |
| `service-describe.json` | `service.describe` 的 result |
| `rpc-response-rejected-stale.json` | 含错误信封的完整 RPC 响应（stale 拒绝示例） |

跨语言验收：Python 与 Node 各自解析全部 fixture → 结构校验 → 产出
key 排序、无空白的 canonical JSON，双方 sha256 摘要表必须一致（摘要表硬编码
在两套契约测试中，任何一方序列化漂移即测试失败）。

## 4. UI 方法 wire 细节

### 4.1 `ui.flow.submit`

- 请求：`{"source": "<NUI 文本>"}`；`idempotency_key` 建议
  `"ui-flow:<uuid>"`。
- 响应 result 即 `flow-submit-result.json` 形态。Python
  `UiProgram.program_revision` 保存的是 `UiProgramRevision` 对象（含
  `program_id`），Node 与 Python 的字段投影必须一致。

### 4.2 `ui.host.inbound`

参数是 `UiHostInbound` tagged union（`kind` 判别，`deny_unknown_fields`）：

| kind | 载荷字段 |
| --- | --- |
| `window_request` | `request: {kind:"data_grid", request: UiDataGridWindowRequest}` |
| `semantic_intent` | `event: UiProgramSemanticEvent` |
| `drag_drop` | `event: UiProgramDragDropEvent`, `active_fragment: UiHostFragmentContext` |
| `data_grid_cell` | `event: UiSemanticEvent` |
| `pointer_event` | `event: UiPointerEvent` |

`UiProgramSemanticEvent`（`deny_unknown_fields`，全部键必发，除
`requested_value` 可省略）：
`event_id, kind, intent, source_node_key, payload, program_revision,
input_revision, request_id, idempotency_key, interaction`。
`kind ∈ {activate, value_tentative, value_commit, selection_changed,
text_edit_commit, interaction_cancel}`。

`UiProgramDragDropEvent`：
`event_id, drag_key, drop_key, intent, payload{source_key, target_key,
placement, presentation_template_key?}, program_revision, input_revision,
request_id, idempotency_key, interaction`。
`placement ∈ {into, before, after}`；`presentation_template_key` 为
`Option`，省略时 runtime 按 `skip_serializing_if` 不发送该键。

宿主校验（runtime 真实行为，SDK 诊断必须能区分）：
- event/request/idempotency/drag/drop/intent/interaction_id 任一为空 →
  `ui_host_invalid_drag_drop` / `ui_host_invalid_semantic_intent`。
- `program_revision` 或 `input_revision` 与 active adapter 不符 →
  `ui_host_stale_drag_drop` / `ui_host_stale_semantic_intent`。
- `interaction.renderer_epoch != 当前 epoch` →
  `ui_host_renderer_epoch_mismatch`。
- source/target key 未在 program 中声明，或 payload 与声明不符 →
  `ui_host_invalid_drag_drop`（SDK 侧归类 `unknown_target`，见 §6）。

### 4.3 `ui.input.frame`

参数即 `UiInputFrame`：`{program_revision, expected_input_revision,
request_id, idempotency_key, changes[]}`；`changes[i] = {key, value:
UiInputValue}`。runtime 侧当前输入 revision 大于
`expected_input_revision` 时以 `ui_program_stale_input_revision` 拒绝
（fixture：`rpc-response-rejected-stale.json`）。

### 4.4 宿主发布（`UiHostPublication`）

宿主在 `ui.host.inbound` 的 accepted 响应 `result` 中返回：

```text
{scalar_frame: UiInputFrame, grid_inputs: UiDataGridInputFrame[], presentation_update?: UiHostPresentationUpdate}
```

- `grid_inputs[i] = {source_key, frame}`；
  `frame = {list_revision, total_rows, first_row, window_rows[],
  expected_program_revision}`；
  `window_rows[i] = {stable_row_key, cells{列名: {value, display,
  presentation_override?}}}`。行身份只用 `stable_row_key`，禁止用数组索引。
- `presentation_update = {expected_fragment_revision, replacement_fragment,
  replacement_program, replacement_input_schema}`，只替换呈现；宿主不得在
  其中夹带输入状态。
- 无 `presentation_update` 时该键省略（`skip_serializing_if`），SDK 模型
  必须容忍缺键并投影为 `null`。

### 4.5 诊断读取

| 方法 | target | result |
| --- | --- | --- |
| `debug.snapshot.get` | ui-runtime | `DebugSnapshot {service, epoch, revision, health, capabilities[], active_jobs[]}` |
| `debug.ui.host.snapshot` | ui-runtime | `UiProgramInputSnapshot {scalar_inputs, grid_inputs}`（canonical 键名见 `program-input-snapshot.json`） |
| `debug.trace.query` | ui-runtime | 参数 `{request_id?, event_id?}` 的 trace 记录列表 |
| `debug.window.input.snapshot` | wgpu-runtime | 窗口输入快照（原始 JSON） |
| `wgpu.render.diagnostics` / `wgpu.render.graph.snapshot` | wgpu-runtime | 渲染诊断 |

## 5. runtime capability 现状（冻结基线）

观察自本机缓存的 runtime 源码与发布件。判定“封装”= SDK 高级 API 是否已
把该能力包装成类型化入口；raw wrapper（直接转发 RPC）不算封装。

### 5.1 `service.describe` 声明的能力

`ui-runtime`（无条件 16 项）：

```text
ui.static_fragment.submit.v1  ui.fragment.submit.v1       ui.image.upload.v1
ui.nine_slice.v1              ui.semantic_input.v1        ui.intent_dispatch.v1
ui.surface.machine.v1         ui.ai.terrain.panel.v1      ui.text_input.commit.v1
ui.program.input.v1           ui.input.repeat.v1          ui.data_grid.window.v1
ui.host.pointer_event.v1      ui.state.animation.v1       ui.numeric.animation.v1
debug.interaction.v1
```

`wgpu-runtime`（基线 15 项 + 条件项）：

```text
基线: wgpu.ui.fragment.v1  wgpu.render.diagnostics  wgpu.ui.hit_target.v1
      wgpu.ui.semantic_event.v1  wgpu.ui.program.semantic_event.v1
      wgpu.ui.render_surface.v1  wgpu.ui.image.upload.v1
      wgpu.ui.image.inspect.v1   wgpu.nine_slice.v1
      wgpu.ui.canvas.points_lines.v1  wgpu.external_host.backend_match.v1
      wgpu.world.info.bridge  wgpu.world.ui.anchor.batch.v1
      wgpu.ui.state.animation.v1  wgpu.ui.numeric.animation.v1
条件(windowed GPU 可用): debug.interaction.v1  wgpu.ai.terrain_generation.v1
条件(lab camera 开):     wgpu.world_ui.lab.camera.v1
条件(debug 构建):        debug.window.capture.v1
```

### 5.2 分类结论

| 能力 | runtime | SDK 封装 | 结论 |
| --- | --- | --- | --- |
| `ui.semantic_input.v1` / `ui.intent_dispatch.v1` / `ui.program.input.v1` / `ui.input.repeat.v1` / `ui.data_grid.window.v1` / `ui.text_input.commit.v1` / `ui.state.animation.v1` / `ui.numeric.animation.v1` | 已声明 | 否（仅 raw） | **已存在未封装** → Stage 003–006 补封装 |
| `wgpu.ui.hit_target.v1` / `wgpu.ui.semantic_event.v1` / `wgpu.world.ui.anchor.batch.v1` / `wgpu.ui.image.upload.v1` / `wgpu.ui.image.inspect.v1` | 已声明 | 否 | **已存在未封装** |
| `wgpu.ui.keyboard.v1` | **未声明**（源码中不存在该 capability 字符串） | Python/Node `InputClient.keyboard` 会检查它 | runtime 尚不存在 → SDK 保留检查并返回 `capability_unavailable`，不得假装可用 |
| `debug.window.capture.v1` | 仅 debug 构建 | `RenderClient.capture` | release runtime 上 capture 属环境限制 → 探针记 `warning`，不算业务失败 |

## 6. 错误 code 冻结

### 6.1 SDK 语义 code（跨语言一致，公共 API 可见）

| code | 触发条件 | retryable |
| --- | --- | --- |
| `stale_revision` | runtime 拒绝原因指向 program/input/fragment revision 过期 | 刷新 snapshot 后可重试一次 |
| `unknown_target` | source/drop/grid key 未在 active program 声明 | 否 |
| `unsupported_intent` | intent 无路由（宿主侧）或 runtime 判定不可派发 | 否 |
| `capability_unavailable` | 所需 capability 不在 describe 结果中 | 否（换 runtime 版本后可） |
| `duplicate_event` | 同 event_id 重放命中幂等表（可视为成功或冲突，两种实现必须一致：SDK 将其作为 `IntentEventResult.status = duplicate` 返回，而非异常） | — |
| `invalid_publication` | 宿主返回 accepted 但 publication 无法应用 | 否 |

### 6.2 runtime 观测 code → SDK code 映射

| runtime code | SDK code |
| --- | --- |
| `ui_program_stale_input_revision` | `stale_revision` |
| `ui_host_stale_semantic_intent` | `stale_revision` |
| `ui_host_stale_drag_drop` | `stale_revision` |
| `ui_host_renderer_epoch_mismatch` | `stale_revision` |
| `ui_host_invalid_semantic_intent` | `unknown_target` 或 `invalid_publication`（按 message 判定：key 未声明 → unknown_target） |
| `ui_host_invalid_drag_drop` | `unknown_target` |
| `ui_host_invalid_publication` | `invalid_publication` |
| `ui_host_response_rejected` | 领域自定义（透传 code，不重映射） |
| `ui_flow_submit_failed` / `ui_program_invalid_*` | `invalid_program`（Stage 002 归入 validate_flow） |

- 未列入映射表的 runtime code 一律以原始 code 透传并附 `details`，禁止吞掉。
- `UiHostInboundResult` accepted 时 result 中的
  `UiProgramSemanticEventResult.status ∈ {accepted, rejected, duplicate}`
  是宿主业务级结果，SDK 必须原样表达，不转换成传输层错误。

### 6.3 revision / epoch / sequence 字段来源（红线）

| 字段 | 唯一合法来源 |
| --- | --- |
| `program_revision.revision` | `ui.flow.submit` 返回 |
| `input_revision` / `expected_input_revision` | 宿主适配器维护；SDK 由 accepted 响应 `revision` 或 snapshot 回读 |
| `renderer_epoch` | 目标服务 `service.health/describe` 的 `epoch`（wgpu 侧重启即 +1） |
| `frame_sequence` | wgpu-runtime 渲染帧计数（snapshot / trace 读取） |
| `fragment.revision` | `debug.snapshot.get` 或 host snapshot |
| `timestamp_unix_ms` | 仅事件信封，由 eventd 写入 |

业务层与 SDK 高级 API 一律不得伪造以上任何字段；raw API 传入时必须与缓存
值一致，否则在执行前抛 `stale_revision`（客户端预判）。

## 7. 版本与兼容

- `protocol.version = {major:1, minor:0}`；minor 演进只允许新增可选键，
  SDK 解析容忍未知键时仅限事件 payload，信封一律 `deny_unknown_fields`。
- runtime 策略：SDK 默认跟随 GitHub `latest` release（`NEON3_RUNTIME_VERSION`
  可固定）；本契约按 v0.2.x 冻结，runtime 若改 wire，必须递增
  `docs/sdk-wire-contract.md` 的 `source_runtime` 并同步 fixture digest 表。
- Python `to_wire()` 与 Node serializer 的输出必须通过 §3 的 digest 表
  验证等价；新增字段先改本文件与 fixture，再改代码。

## 8. Stage 000 验收状态

- [x] canonical fixture 10 份（含 1 份错误信封）落盘 `docs/fixtures/wire/`
- [x] Python `neon3_sdk.wire`：canonical JSON、fixture 加载、字段校验工具
- [x] Python 契约测试 `tests/test_wire_contract.py`
- [x] Node 契约测试 `src/test/contract.test.ts` + `src/wire.ts`
- [x] 跨语言 digest 表一致（同一组 sha256 硬编码在两侧测试）
- [x] 错误 code 冻结（§6）与 capability 分类（§5）
