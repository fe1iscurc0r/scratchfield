# RF-Agent 频谱扫描调度层设计稿

> 工单205 任务二 · 出单：沈遥 · 设计：砚 · 2026-10-07
> 来源：**2610.05485 RF-Agent**（层级语言 Agent 控制主动频谱感知）+ **2610.04296 RRM-GPT**（无线资源管理基础模型愿景）
> **性质：参考级**（借架构思想，**不搬代码**）。绑定"频谱界面重制定位81"重构，**本稿只设计不实现**。

## 0. 为什么借这套架构

RF-Agent 的核心主张：频谱感知不该是"一套参数配一个扫描"，而应由**语言指令**驱动分层决策——
*听懂了要什么 → 规划成设备可执行的扫描序列 → 交给硬件执行*。
scratchpad 现状是**反过来的**：`rf_brain` 有决策层（`decision_layer.decide()`）但入口是**特征向量**，
不是语言；前端 `SpectrumPanel.vue`（951 行）既发参数又画图。本稿把这套分层补齐。

## 1. 三层映射（RF-Agent → scratchpad）

| RF-Agent 层 | 职责 | scratchpad 对接点（实测） | 现状 | 动作 |
|---|---|---|---|---|
| **① 指令理解** | 自然语言 → 结构化扫描意图 | **无现成入口** | ❌ 空白 | **新建**（本稿 §2 的解析规则表） |
| **② 任务规划** | 意图 → 扫描参数序列（含模式/时长/带宽） | `rf_brain/decision_layer.py`：`decide(fv: FeatureVector) -> Decision`；内部 `_llm_available()` / `_build_prompt()` / `_call_llm()` / `_fallback_decision()` | ⚠️ 有，但入口是特征向量 | **复用**：把 §2 的结构化意图喂成 `FeatureVector` 的补充维度，或新增 `plan_from_intent()` 并行入口 |
| **③ 设备执行** | 执行扫描、回收帧 | `rf_brain` 工具面：`analyze_signal` / `generate_and_analyze` / `spectrum_events.ingest_frame` / `spectrum_events.current_interferers` / `spectrum_events.recent_events`（manifest 实测 8 工具中的 5 个） | ✅ 已有 | **不改**（调度层只编排，不碰 DSP） |

**关键判断**：③ 已经够用（`spectrum_events.*` 就是"执行 + 状态查询"的面），
缺口在 ①②之间的**语言 → 参数**这一段 —— 这正是 RF-Agent 值得借的部分。

## 2. 指令解析规则表（语言 → 扫描参数）

结构化意图字段（与 `Decision` 对齐）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `freq_center_hz` | float | 中心频率 |
| `bandwidth_hz` | float | 带宽 |
| `duration_s` | float | 持续时长 |
| `mode` | str | 解调模式（ft8 / cw / ssb / wideband…） |
| `target` | str | 搜索目标（可选，供规划层加权） |
| `priority` | int | 优先级（默认 0） |

**解析规则**（按"频段 → 带宽 → 目标 → 时长"四步，缺项用缺省）：

| 语言片段 | 解析结果 | 规则 |
|---|---|---|
| `7MHz` / `40米` / `40m` | `freq_center_hz = 7.074e6`（FT8 段）或 7.0e6（裸频段） | **业余频段表**：已有 `rf_brain/amateur_bands.py` ✅ **直接复用**，不新建表 |
| `上` / `下` + 频段 | 取该段中心 | — |
| `5 分钟` / `30秒` | `duration_s = 300 / 30` | 时间单位归一 |
| `找 FT8` / `FT8` | `mode = "ft8"`, `bandwidth_hz = 3000`（FT8 惯例 3kHz）, `target = "ft8"` | 模式 → 带宽缺省绑定 |
| `扫一遍` / 未给时长 | `duration_s = 60`（缺省） | — |
| `找 CW` | `mode = "cw"`, `bandwidth_hz = 500` | 同上 |
| 带宽显式（`20kHz 带宽`） | 覆盖模式缺省 | 显式优先 |

**歧义处理**：无法解析的片段**不猜**——返回 `{status: "error", error: "unparsed", detail: "<原片段>"}`，
由前端提示用户改写（与仓库"不静默降级"口径一致）。

**示例**：

| 指令 | 解析结果 |
|---|---|
| `扫 7MHz 上 5 分钟找 FT8` | `{freq_center_hz: 7.074e6, bandwidth_hz: 3000, duration_s: 300, mode: "ft8", target: "ft8"}` |
| `40 米段扫 30 秒看 CW` | `{7.0e6, 500, 30, "cw", "cw"}` |
| `看看 144MHz 有没有信号` | `{144.0e6, 缺省, 60, "wideband", null}` |

## 3. 与 Lumo 频谱面板的接口约定

**边界原则：前端只发指令、显示状态；调度全在服务端。**

| 方向 | 接口 | 载荷 |
|---|---|---|
| 前端 → 服务端 | `POST /api/rf/scan_intent` | `{text: "扫 7MHz 上 5 分钟找 FT8"}` |
| 服务端 → 前端 | 同上响应 | `{status: "ok", intent: {...§2 字段}, session_id}` 或 `{status:"error", error:"unparsed", detail}` |
| 前端 → 服务端 | `GET /api/rf/scan_status?session_id=` | 轮询（与现有 `spectrum_events.*` 查询口径一致） |
| 服务端 → 前端 | 状态 | `{state: "planning\|scanning\|done\|failed", progress, frames_seen}` |
| 前端展示 | 复用现有面板 | 参数展示 + 进度 + 结果曲线（**前端不再计算扫描参数**） |

**`SpectrumPanel.vue`（951 行）的改造方向**（与工单204 任务三的拆分绑定）：
把"参数表单 + 直接调 DSP"的部分**下沉到服务端**，前端只留"输入框 + 状态区 + 图表"三块 ——
这同时是"频谱界面重制定位81"重构的一部分，**两张工单在此收敛**。

## 4. 明确不做的（参考级边界）

| 项 | 原因 |
|---|---|
| 搬 RF-Agent 代码 | 论文是**参考级**；且其实现绑定特定 SDR 栈，与 `rf_brain` 的 DSP 链不通 |
| 实现语言解析器 | 本稿**只设计**；实现待"频谱界面重制定位81"重构方案定稿后一并排期 |
| 改 `decision_layer.decide()` 签名 | 它是现有调用方的契约；新入口若需要，**并行新增**而非改签名 |
| 引入 LLM 解析（语言 → 参数） | 规则表已能覆盖常见指令；LLM 解析作为**第二步**（规则未命中时兜底），避免一来就依赖模型可用性 |

## 5. 落地检查点（供未来实现时自检）

1. 解析规则表**每条都有测试**（含歧义不猜的负例）；
2. 频段数据**复用 `amateur_bands.py`**，不新建第二份频段表（☠️ 双源必漂移）；
3. 前端不再出现扫描参数计算逻辑（`SpectrumPanel` 只发指令）；
4. 调度层**不碰 DSP**（③ 层保持现状）。

— 砚 · 工单205 任务二 · 只设计不实现，参考级已标注
