# NUI Flow 入门教程（视频大纲）

> 面向：用过 Web 前端（HTML/CSS/React）的开发者
> 目标：看完就能写自己的 NUI Flow 界面

---

## 第一章：宏观原理（和 Web 前端类比）

### 1.1 NUI Flow 是什么

一句话：**NUI Flow 是一个纯声明式的 UI 描述语言，跑在 Neon3 Runtime 里。**

| Web 前端 | NUI Flow |
|---|---|
| HTML | NUI Flow（结构） |
| CSS | NUI Flow 属性（fill / w / h / pad...） |
| React useState | `input` 类型化输入 |
| React onClick | `event` 语义 intent |
| React useEffect | `machine` 状态机 |
| React conditional render | `branch` |
| React map + list | `repeat` / `template` |

### 1.2 为什么不用 JS / TS？

NUI Flow **故意没有**：
- 没有 JavaScript
- 没有回调函数
- 没有表达式（不能写 `a + b`）
- 没有 DOM API

**为什么？** 因为 NUI Flow 是给 GPU 渲染的声明式文档，不是给人执行的代码。
所有逻辑都在**外部域服务**（你的 Python/Node/Rust 程序）里跑，Flow 只负责"长什么样"和"用户点了什么按钮"。

### 1.3 整体架构

```
你的程序 (Python/Node/Rust)          NUI Flow 文档
┌─────────────────────┐              ┌─────────────────────┐
│ 业务逻辑             │              │ 界面结构             │
│ 数据处理             │ ──────────>  │ surface / button     │
│ API 请求             │              │ input / machine      │
│ 状态管理             │ <──────────  │ event intent         │
└─────────────────────┘              └─────────────────────┘
         │                                      │
         └────────── TCP RPC ──────────────────┘
                        │
                ┌───────▼───────┐
                │ Neon3 Runtime  │
                │  (wgpu 渲染)   │
                └───────────────┘
```

**数据流：**
1. 你的程序把数据通过 `input` 喂给 Flow
2. Flow 根据数据渲染界面
3. 用户点按钮 → Flow 发出 `event` 语义 intent
4. 你的程序收到 intent → 处理业务逻辑 → 更新数据 → 回到第 1 步

### 1.4 核心概念速览

| 概念 | 作用 | 类比 |
|---|---|---|
| `surface` | 一个窗口/画布 | `<body>` |
| `panel` | 容器/分组 | `<div>` |
| `text` | 文字 | `<span>` |
| `button` | 按钮 | `<button>` |
| `input` | 类型化数据入口 | `useState` |
| `$var` | 引用输入 | `{state.var}` |
| `event` | 语义事件 | `onClick` |
| `machine` | 状态机 | `useReducer` |
| `branch` | 条件渲染 | `{cond && <Comp/>}` |
| `repeat` | 列表 | `.map(item => <Item/>)` |

---

## 第二章：第一个 Hello World

### 目标
一个窗口，居中显示一行文字。

### 代码

```text
surface demo column w 400 h 200 align center middle fill #101820
  text hello value "Hello, Neon3!"
```

### 逐行解释

| 行 | 代码 | 含义 |
|---|---|---|
| 1 | `surface demo` | 声明一个 surface，名字叫 demo |
| 1 | `column` | 子元素垂直排列（像 CSS flex-direction: column） |
| 1 | `w 400 h 200` | 宽 400，高 200 |
| 1 | `align center middle` | 子元素水平居中、垂直居中 |
| 1 | `fill #101820` | 背景色深蓝 |
| 2 | `text hello value "..."` | 一个 text 节点，显示文字 |

### 视频要点
- NUI Flow 是缩进驱动的（像 Python），不是 HTML 那种闭合标签
- 所有属性都是 `key value` 空格分隔
- 字符串用双引号，颜色用 `#RRGGBB`

---

## 第三章：布局——row / column / panel

### 目标
一个工具栏：左边标题，右边按钮。

### 代码

```text
surface main column w 800 h 600 fill #101820

  panel toolbar row h 48 pad 12 fill #203040
    text title value "My App"
    button save value "Save" event app.save
```

### 关键属性

| 属性 | 作用 | CSS 类比 |
|---|---|---|
| `row` | 水平排列子元素 | `display: flex; flex-direction: row` |
| `column` | 垂直排列子元素 | `display: flex; flex-direction: column` |
| `w / h` | 宽 / 高 | `width / height` |
| `pad` | 内边距 | `padding` |
| `gap` | 子元素间距 | `gap` |
| `align` | 子元素对齐 | `align-items / justify-content` |
| `fill` | 背景色 | `background-color` |

### 视频要点
- `panel` 是最常用的容器，可以嵌套
- 布局是 flexbox 模型，但更简单（没有 wrap、没有 order）
- 所有尺寸都是逻辑像素（不是物理像素）

---

## 第四章：类型化输入——input + $引用

### 目标
显示一个动态标题，标题内容由外部程序控制。

### Flow 代码

```text
input title text default "Untitled"

surface main column w 800 h 600 fill #101820
  panel toolbar row h 48 pad 12 fill #203040
    text title value $title
```

### 外部程序（Python 示例）

```python
from neon3_sdk import start, mount, state

with start() as app:
    mount("my.nui")
    app.set_input("title", "Hello from Python!")
```

### 关键概念

| 语法 | 含义 |
|---|---|
| `input title text default "Untitled"` | 声明一个 text 类型的输入，默认值是 "Untitled" |
| `value $title` | 引用这个输入，`$` 是引用符号 |

### 支持的输入类型

| 类型 | 示例 | 用途 |
|---|---|---|
| `bool` | `input enabled bool default true` | 开关/勾选 |
| `i32:0..100` | `input progress i32:0..100 default 0` | 进度/滑块 |
| `f32:0..1` | `input amount f32:0..1 default 0.5` | 浮点参数 |
| `enum:a\|b\|c` | `input choice enum:alpha\|beta default alpha` | 单选 |
| `text` | `input name text default "..."` | 短文本 |

### 视频要点
- NUI Flow **没有变量**，只有"输入"——所有数据都从外部喂进来
- `$xxx` 就是引用这个输入，像 React 里的 `{state.xxx}`
- 输入是**类型安全的**，有界的（不能写无限范围）

---

## 第五章：按钮 + 事件

### 目标
点按钮，外部程序收到通知。

### Flow 代码

```text
input count i32:0..999 default 0

surface main column w 400 h 200 align center middle fill #101820
  text count value "Count: $count"
  button inc value "Increment" event app.increment
```

### 外部程序

```python
with start() as app:
    mount("counter.nui")

    @app.on("app.increment")
    def _():
        current = app.get_input("count")
        app.set_input("count", current + 1)
```

### 关键概念

| 语法 | 含义 |
|---|---|
| `event app.increment` | 点击按钮时发出语义事件 `app.increment` |

### 视频要点
- `event` 是**点分语义命名**，不是回调
- 按钮不直接改状态——它只发"我被点了"这个信号
- 外部程序收到信号后，决定怎么改数据
- 这就是单向数据流：外部 → input → 渲染，用户交互 → event → 外部

---

## 第六章：状态机——machine / state

### 目标
一个按钮：点击后变成"加载中"，3 秒后变成"完成"。

### Flow 代码

```text
input status enum:idle|loading|done default idle

machine submit_btn initial idle
state submit_btn loading
state submit_btn done

on submit_btn app.submit when $status=idle -> loading emit app.submit.do
sync submit_btn when $status=done -> done

surface main column w 400 h 200 align center middle fill #101820
  button submit value "Submit" event app.submit
```

### 逐行解释

| 行 | 含义 |
|---|---|
| `machine submit_btn initial idle` | 声明一个状态机，初始状态 idle |
| `state submit_btn loading` | 允许进入 loading 状态 |
| `on submit_btn app.submit when $status=idle -> loading` | 收到 `app.submit` 事件，且当前是 idle → 切换到 loading |
| `sync submit_btn when $status=done -> done` | 外部 `status` 输入变成 done → 切换到 done |

### 视频要点
- 状态机只管理**UI 表现状态**（按钮文字、颜色、禁用）
- 业务数据（status）还是外部喂进来的
- 状态机是**有限的**——不能无限跳变，所有状态都必须提前声明
- 没有 if/else，所有跳转都是预声明的

---

## 第七章：条件渲染——branch

### 目标
根据状态显示不同内容：加载中显示 spinner，就绪显示内容。

### Flow 代码

```text
input status enum:loading|ready|error default loading

surface main column w 400 h 300 fill #101820

  branch loading-view when $status=loading
    text msg value "Loading..."

  branch ready-view when $status=ready
    text msg value "Content loaded!"

  branch error-view when $status=error
    text msg value "Something went wrong" fill #FF6B6B
```

### 视频要点
- `branch` 就是条件渲染，像 React 的 `{cond && <Comp/>}`
- 所有分支都要提前声明，不能运行时动态加
- 分支之间互斥（虽然语法上允许同时满足，但实际使用时会设计成互斥）

---

## 第八章：列表——repeat / template

### 目标
显示一个待办事项列表。

### Flow 代码

```text
input todos list:todo default list:empty

template todo-item h 32 key item_id
  row h 32 pad 8
    text title value $item_title

surface main column w 400 h 600 fill #101820
  repeat todo-list h 500 capacity 100 key item_id
```

### 外部程序

```python
app.set_input("todos", [
    {"item_id": 1, "item_title": "Learn NUI Flow"},
    {"item_id": 2, "item_title": "Build an app"},
])
```

### 视频要点
- `repeat` 是有界列表（capacity 100），不是无限的
- `template` 定义每行长什么样
- 每行的 key 必须稳定（item_id），像 React 的 key prop
- 大数据列表（几千行）不会卡顿——runtime 只渲染可见的行

---

## 第九章：样式——fill / font / fx

### 目标
做一个带发光效果的标题。

### Flow 代码

```text
text_style neon-title
  fill #6EF3C5
  fx glow intensity 1.2 radius 8 color #6EF3C5
  fx sweep color #FFFFFF width 24 period 3.5

surface main column w 800 h 200 align center middle fill #101820
  text title style neon-title value "Welcome to Neon3"
```

### 内置 fx 清单

| fx | 效果 | 参数 |
|---|---|---|
| `glow` | 外发光 | color, radius, intensity |
| `outline` | 描边 | color, width |
| `soft_shadow` | 软阴影 | offset, blur, color |
| `gradient` | 渐变填充 | from, to, angle |
| `sweep` | 流光扫过 | color, width, period |
| `wave` | 波动 | amplitude, frequency, speed |

### 视频要点
- `text_style` 是全局命名样式，定义一次到处用
- fx 是 GPU shader 做的，性能很好
- 最多叠加 2 层 fx（防止性能爆炸）

---

## 第十章：完整小应用——计数器

### 目标
一个完整的计数器：加、减、重置。

### Flow 代码 (`counter.nui`)

```text
input count i32:0..999 default 0
input can_decrement bool default false

machine counter_btn initial idle
state counter_btn negative

on counter_btn app.decrement when $can_decrement -> negative
sync counter_btn when $count > 0 -> idle

surface counter column w 300 h 200 align center middle gap 16 fill #101820

  text count display "Count: $count"

  panel controls row gap 8
    button dec value "-" event app.decrement
    button inc value "+" event app.increment
    button reset value "Reset" event app.reset
```

### 外部程序 (Python)

```python
from neon3_sdk import start

with start(origin="counter-demo") as app:
    app.mount_flow(open("counter.nui").read())

    @app.on("app.increment")
    def _():
        c = app.get_input("count")
        app.set_input("count", c + 1)
        app.set_input("can_decrement", True)

    @app.on("app.decrement")
    def _():
        c = app.get_input("count")
        if c > 0:
            app.set_input("count", c - 1)

    @app.on("app.reset")
    def _():
        app.set_input("count", 0)
        app.set_input("can_decrement", False)

    app.run()  # 阻塞，直到窗口关闭
```

### 视频要点
- 这就是 NUI Flow 的完整闭环：
  1. 声明输入（count）
  2. 声明界面（显示 count + 三个按钮）
  3. 声明事件（increment / decrement / reset）
  4. 外部程序监听事件 → 改输入 → Flow 自动重渲染
- 没有虚拟 DOM、没有 diff、没有 useEffect——改 input 就是改 state，Flow 自动重渲染

---

## 附录：NUI Flow 禁止做的事

| 禁止 | 为什么 |
|---|---|
| 写 JavaScript / Python | Flow 是声明式文档，不是代码 |
| 写回调函数 | 所有逻辑都在外部域服务 |
| 写表达式（`a + b`） | Flow 不能计算，只能展示 |
| 写 URL / 文件路径 | 安全边界 |
| 写 GPU handle / 像素坐标 | 抽象层级太高 |
| 动态加节点 / 删节点 | 拓扑固定，只有数据变 |
| 在 Flow 里做权限判断 | 所有权限逻辑在外部 |

---

## 视频录制建议

| 集数 | 主题 | 时长建议 |
|---|---|---|
| 第 1 集 | 宏观原理：NUI Flow 和 React 的类比 | 5 分钟 |
| 第 2 集 | Hello World：第一个窗口 | 3 分钟 |
| 第 3 集 | 布局：row / column / panel | 5 分钟 |
| 第 4 集 | 输入：类型化数据绑定 | 5 分钟 |
| 第 5 集 | 事件：按钮点击通知外部 | 5 分钟 |
| 第 6 集 | 状态机：加载 / 就绪 / 错误 | 7 分钟 |
| 第 7 集 | 条件渲染：branch | 3 分钟 |
| 第 8 集 | 列表：repeat / template | 5 分钟 |
| 第 9 集 | 样式：text_style + fx | 5 分钟 |
| 第 10 集 | 完整案例：计数器 | 8 分钟 |
| **总计** | | **~51 分钟** |
