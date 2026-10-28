# 工单 263 · GitHub 扫货日报 10-19 落地（Top3 三件套 + 6 维 15 项 / 守卫 FAIL=0 / 9 已扫去重 / 5 暂缓排除）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-263 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_263.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-263-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_263.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 10-19 在 QQ 下令"把授粉、论文、日报全部转换成工单"。本单对应**日报**类（10-19 早上 09:05 沈遥落盘的扫货日报）。
> **素材漏斗**：`docs/GitHub-Sweep-Daily-2026-10-19.md`（106 行 / 13 KB / 6 维度 × 15 项）
> **守卫**：anti_hallucination_guard FAIL=0 / WARN=17（10 已扫 / 3 NOASSERTION / 2 无 LICENSE / 2 修正项）
> **前序**：WO-240（10-15 sweep 单）2026-10-17 师傅 10-17 拍板**不复活**（时点性产物，被新日报自然覆盖）→ **本工单是新一期**日报的标准转化流程

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 15 项入表全部 `gh api` 实核 | ✅ | 见日报 §①-⑥ |
| 2 | 6 维分类 | ✅ | Live2D/桌宠 / 语音 / 材料·化学 / 记忆·KG / 桌面·前端 / MCP |
| 3 | Top 3 选定 + 次席 1 项标注 | ✅ | psd2live / ayagami / breeze-tts + solid-glass（次席因太新） |
| 4 | 9 项去重 / 5 项暂缓排除 | ✅ | 见日报 §去重记录 |
| 5 | 15 项每项落 1 份评估 md | ❌ | 本工单任务 A |
| 6 | Top 3 真接入（含 commit / SPEC / 验收） | ❌ | 本工单任务 B-D |
| 7 | "5 暂缓/排除"反向激活路径 | ❌ | 本工单任务 E |

**核心痛点**：
- 10-15 那次 WO-240 没落地就过期了——**这次的转化流程不能重复**：日报本身就是 6 维分类表，不需要再让 Trae 重排
- Top 3 是本期最高价值（`psd2live` NEKO 资产管线断点补齐 / `ayagami` 摆脱 Cubism 闭源 / `breeze-tts` 伴侣角色语音情绪），不施工就是放着过期
- 扫货日报的"评估报告"是 **Read-Only 侦察产物**（不是立项），要让 Trae 区分"评估"和"立项施工"两层

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 把 15 项入表候选按 3 档分桶（🥇Top3 真接入 / 🥈次席评估不并码 / 🥉贴手未入前 15 备选评估），每档 1 份评估 md + Top 3 各 1 份立项 SPEC/工单 |
| **M** Measurable | ① 15 项评估 md 全落 `docs/扫货-eval/2026-10-19/`；② Top 3 真接入（合并入 NEKO / Lumo / 语音）；③ 次席 1 项评估不并码（只读 SPEC）；④ 5 暂缓/排除反向激活路径表；⑤ 守卫 FAIL=0 |
| **A** Achievable | 评估 md 模板化（项目 / 协议 / 架构 / 授粉价值 / 难度×收益 / 接入模式 6 段），15 份可批处理；Top 3 接入已由 10-19 沈遥的"对 scratchpad 的价值"列写好骨架 |
| **R** Relevant | 师傅四条主方向：MCP / Live2D 桌宠 / 知识图谱记忆 / 材料科研；NEKO 资产管线 / Lumo 前端换皮 / 语音三件套全打中 |
| **T** Time-bound | 1 周（W2 与 WO-262/264 同期 review） |

## §2 · 任务清单

### 任务 A · 15 项评估 md 落仓

新目录 `docs/扫货-eval/2026-10-19/`：

- 15 份 `eval-<owner>-<repo>.md`，每份含 6 段：
  1. **项目**：1 段（定位 / 星数 / 许可 / 体积 / 维护活跃度）
  2. **协议**：架构图、入口点、关键 API
  3. **本侧对照**：与 scratchpad 哪个模块对应
  4. **授粉价值**：3 条借鉴点（按日报原文）
  5. **难度×收益**：低/中/高 × 低/中/高
  6. **接入模式**：MCP / Skill / 融合参考 / 设计输入 / 不引入
- 文件命名严格 `<owner>-<repo>`，避免歧义
- 模板：`docs/扫货-eval/_template.md`（**不计入 15**）

**验收**：`ls docs/扫货-eval/2026-10-19/ | wc -l` ≥ 15；每份 md ≥ 30 行

### 任务 B · 🥇Top3-1 `tsunehimatoi/psd2live` 接入（NEKO 资产管线）

定位：补 NEKO 资产管线（PSD → 可动模型）。

- **许可分割**：仓库是 GPL-3.0+MIT 双段
  - 引擎 `umamo`（GPL-3.0）→ **不并码**
  - 中立绑定 IR `format-model`、导出框架 `format-compile`、Rust 运行时（MIT）→ **可单独复用**
- **接入模式**：**离线资产工具链**（本地 CLI），不进主仓二进制
- **落点**：
  - `tools/psd2live-bridge/`：包装 MIT 段（不引入 GPL 主程序）
  - `docs/SPEC-neko-asset-pipeline-2026-10.md`：从 PSD 制作 Live2D 模型的标准流程
- **验收**：
  - `tools/psd2live-bridge/` 有 1 个 shell 入口 + 1 个 README
  - `git log --all --oneline -- tools/psd2live-bridge/ \| wc -l` ≥ 1
  - 仓库体积检查：clone `--depth 1` 后的体积 ≤ 5 MB（只取 MIT 段）

### 任务 C · 🥇Top3-2 `AyagamiDev/ayagami` 接入（摆脱 Cubism 闭源）

定位：法务级依赖解耦（Cubism SDK 闭源带商用条款，NEKO 越做越深越受制）。

- **许可**：MIT + Apache-2.0 双许可
- **接入模式**：**核心依赖**（NEKO 桌宠渲染路径替换）
- **特殊警示**：`LICENSE-MIT` + `LICENSE-APACHE` 是**非标准名**（只查 `LICENSE` 会误判无许可）
- **落点**：
  - `docs/operate/cubism-deprecation-roadmap.md`：替换时序（保留 Cubism 6 个月兼容期 → 切 Ayagami）
  - 调研：Ayagami 当前是否覆盖 NEKO 所需的全部 Cubism 特性
- **验收**：
  - `docs/operate/cubism-deprecation-roadmap.md` ≥ 3 阶段（调研/灰度/全量）
  - 1 段"差异矩阵"（Ayagami vs Cubism 缺失的 API）

### 任务 D · 🥇Top3-3 `breezeblue-ai/breeze-tts` 接入（伴侣角色语音情绪）

定位：伴侣角色语音短板是"情绪与停顿假"，Breeze TTS 2 把 `[笑]`/`[叹气]` 直接写进文本、双语单模型、许可干净。

- **许可**：Apache-2.0
- **接入模式**：**Provider 模式**（进 NEKO TTS 抽象层，1 条 provider 即可）
- **落点**：
  - `mcpserver/tts_providers/breeze.py`：实现 `synthesize(text, voice_id, emotion_events) -> Audio`
  - 注册到 `mcpserver/tts_providers/registry.py`
  - 1 个样例：伴侣"她"角色的日常对话带 1-2 个情绪事件
- **验收**：
  - `python -c "from mcpserver.tts_providers import breeze"` 无异常
  - 样例音频文件可播放（`file output.wav` 报 RIFF）
  - 若官方榜属实标注：在 README 加 1 段 "vs OmniVoice 对照"

### 任务 E · 5 暂缓/排除 反向激活路径表

新文件 `docs/sweep/deferred-2026-10-19.md`：

| 项目 | 裁决 | 反向激活路径 |
|---|---|---|
| `VictorTaelin/OptMem` 2208★ 无 LICENSE | 暂缓 | 426-token 提示概念值得读；若作者补 LICENSE 可下一轮 re-eval |
| `kevinzhow/Rungic` 415★ 无 LICENSE | 暂缓 | 与 `phone-mobile-hub` 撞题；待 `phone-mobile-hub` 项目开单后回头对 |
| `Nomily-Ai/nomily-app` 797★ Source-available | 硬排除 | 不可激活；伪开源 |
| `jaredrhod/fullstack-agent` 1119★ AGPL 但 68KB Batchfile | 硬排除 | 仅作架构故事读，无可复用代码 |
| `mrpulor-gh/nuphus-mcp` MIT 重叠 | 重叠 | 10-18 已入表的 Linux 桌面控制 MCP 同层，不重复评估 |

**验收**：5 行齐全，"反向激活路径"列每行 ≥ 10 字

### 任务 F · 次席 1 项评估不并码

`deeplethe/solid-glass` 2049★ MIT（10-12 建仓一周破 2000 星）：

- **特别提示**：建仓仅 7 天，**API 稳定性未确认**
- **落点**：`docs/扫货-eval/2026-10-19/eval-deeplethe-solid-glass.md`（不并码）
- 评估含 1 段"6 个月后再 re-eval"的触发条件（如：发版节奏 ≥ 1 release/month、token 数量 ≥ 50、API breaking change 频次 ≤ 1/quarter）

## §3 · 验收标准

| 项 | 阈值 | 验收命令 |
|---|---|---|
| 1. 15 评估 md 全落仓 | 15 份 | `ls docs/扫货-eval/2026-10-19/ \| wc -l` ≥ 15 |
| 2. 模板文件 | 1 份 | `ls docs/扫货-eval/_template.md` 存在 |
| 3. Top 3-1 psd2live 接入 | tools/ + SPEC | `ls tools/psd2live-bridge/ \| wc -l` ≥ 2 + SPEC 存在 |
| 4. Top 3-2 ayagami 调研 | deprecation roadmap | `ls docs/operate/cubism-deprecation-roadmap.md` 存在 |
| 5. Top 3-3 breeze 接入 | provider + 样例音频 | 见任务 D 验收 |
| 6. 5 暂缓/排除表 | 5 行齐全 | `wc -l docs/sweep/deferred-2026-10-19.md` ≥ 5 |
| 7. 次席评估 + 6 月触发条件 | 1 份 | `ls docs/扫货-eval/2026-10-19/eval-deeplethe-solid-glass.md` 存在 |
| 8. 守卫 FAIL=0 | 0 | `python tools/anti_hallucination_guard.py --check-report docs/GitHub-Sweep-Daily-2026-10-19.md` |
| 9. 不抢 40/42 已有 NEKO 链 | `git diff --stat -- NEKO` 仅 task 涉及行 | `git diff --stat main -- NEKO \| wc -l` ≤ 50 |

## §4 · 关联

- **WO-262**（授粉轮 46 落地）：同期同批，PR 一起合
- **WO-264**（论文日报转化）：同期同批，PR 一起合
- **WO-240**（10-15 日报单）：**不复活**（10-17 拍板），本单是新一期日报的标准流程
- **WO-259/260**（10-17 复活的 WO-238/239/240）：**与本工单无交叉**，本工单是 WO-240 之后的**新一期**
- **NEKO 资产管线**（已有）：与本工单任务 B 衔接
- **Lumo 前端换皮**（已有）：与本工单任务 F 衔接

## §5 · 风险与边界

| 风险 | 缓解 |
|---|---|
| 任务 B 误并 GPL 主程序 | 文档明示"只取 MIT 段"；接入模式审"非主仓二进制" |
| 任务 C Ayagami 不全覆盖 Cubism | "差异矩阵"段写明缺失项；保留 6 个月兼容期 |
| 任务 D breeze 自宣榜（Artificial Analysis 开放权重第一）未核实 | README 标"待核实"；不作为接入门槛 |
| 任务 E 反向激活路径漏写 | 5 行必填 |
| 任务 F solid-glass 6 月后被 fork 抢走 | 触发条件清单化，季度复盘 |
| 评估 md 数量大（15 份）| 模板化批处理，Trae 用 `for f in` 跑 |

**不在本工单范围**：
- 9 已扫/已授粉项的二次评估（按日报原文"本期不重复立项"）
- 备选 3 项（FireRedTTS3 / nvalchemi-toolkit / ChemoSuite）的接入（其中 nvalchemi-toolkit 已授粉）
- Cubism SDK 当前用户的迁移（保留 6 个月兼容期，不在 263 范围）

## §6 · 落地物清单

| 类别 | 文件 | 数量 |
|---|---|---|
| 评估 md | `docs/扫货-eval/2026-10-19/eval-<owner>-<repo>.md` | 15 |
| 模板 | `docs/扫货-eval/_template.md` | 1 |
| Top 3-1 接入 | `tools/psd2live-bridge/{cli, README}` + `docs/SPEC-neko-asset-pipeline-2026-10.md` | 2 + 1 SPEC |
| Top 3-2 调研 | `docs/operate/cubism-deprecation-roadmap.md` | 1 |
| Top 3-3 接入 | `mcpserver/tts_providers/breeze.py` + `mcpserver/tts_providers/registry.py` 注册 + 样例 | 2 + 1 样例 |
| 反向激活路径表 | `docs/sweep/deferred-2026-10-19.md` | 1 |
| 次席评估 | `docs/扫货-eval/2026-10-19/eval-deeplethe-solid-glass.md` | 1 |

## §7 · 编号防撞

- **指令文件**：`TRAE_WORKORDER_PROMPT_AGENT_263.md`（仓库根，input）
- **施工记录**：本文件 `docs/WO-263-*`（output）
- 与已发的 `TRAE_WORKORDER_PROMPT_AGENT_*` 不撞号（已用 254~262，**263 下一号**）
