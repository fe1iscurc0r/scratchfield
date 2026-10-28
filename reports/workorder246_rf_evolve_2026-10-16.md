# 工单 246 完工报告 · RF 算法演化框架（`mcpserver/rf_evolve/`）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）
> 日期：**2026-10-16** · 基线：main `ea1c0258ea20`（工单245 合并点）
> 工单来源：`TRAE_WORKORDER_PROMPT_AGENT_246.md`（`cron_to_workorder` 自动草稿 → 师傅签字晋升，PR #347）
> 范式来源：**SeisEvo**（arXiv:2608.18272v1，Xu/Yu/Ma，2026-08-18）——*Seismic Data Reconstruction Algorithms by Agents*
> 交付：**12 个新文件，0 个既有文件改动**（零侵入）

---

## §0 · 交付事实

| 项 | 值 |
|---|---|
| 新增文件 | **12**（模块 9 + 集成图 1 + sandbox 9（含白盒产物）+ 测试 1 + 本报告 —— 明细见 §3） |
| 既有文件改动 | **0**（`rf_brain` / `mcp_manager` / `mcp_registry` 都没动） |
| 新增第三方依赖 | **0**（只用 numpy —— 仓内既有依赖） |
| 测试 | **55 用例全绿**（`tests/test_rf_evolve.py`） |
| `ruff check .` | **All checks passed**（含**生成的白盒产物**） |
| 真跑证据 | `sandbox/rfe-20261016-rfi-mitigation/` 9 份（含**白盒产物本体**及其独立自检） |

### 核心读数（一次真实运行，0.4 s）

| | 均值（3 场景） | 最差场景 |
|---|---|---|
| 仓库默认参数 | **+6.7658 dB** | +3.3958 dB |
| 演化所得 | **+16.4679 dB** | **+12.9993 dB** |
| **提升** | **+9.7021 dB** | **+9.6035 dB** |

约束门：**17 提案 / 5 在 B 段被否 / 12 进入打分 / 省下 3,002,368 次样本运算**。

---

## §1 · 工单 §4 的填实（草稿留白，由本单补）

| §4 项 | 本单结论 |
|---|---|
| **PoC 边界与验收标准** | **边界**：只做**离线数值实验** —— 演化「窄带干扰抑制」的参数组；不实现滤波算法（被演化算法在 `rf_brain`，冻结）、不做硬件在环、不做真实发射。**验收**：① 演化所得必须优于仓库默认（**均值与最差场景都要好**）；② 每条约束都有单测证明它能否决；③ 白盒产物**能独立 exec**、**与 harness 逐位一致**、**不 import 本仓**；④ 55 用例全绿。 |
| **与现有模块的耦合点** | 被演化算法与评分函数：`mcpserver/rf_brain/rfi_mitigation.py`（**只读**）；落点：`mcpserver/rf_evolve/`（新）。与 `rf_workflow`(242) 的划界见 §2.2。 |
| **是否与已发工单重复** | **不重复**（244j 已代查：根目录 45 个工单对 `2608.18272` / `SeisEvo` 零命中）。与最相邻的 242 是**互补**关系（242 = 单次生成仿真脚本；本单 = 受限面上的演化搜索），详见 §2.2。 |

---

## §2 · 设计决策

### 2.1 为什么**不**自己造一套 DSP

仓内已有 `rf_brain/rfi_mitigation.py`（RFI 检测 + 陷波链 + LMS 自适应对消 + `_snr_db` 评分），
它正是工单 §0 说的「干扰检测与抑制」。**另造一个玩具 DSP 会让本单变成两件事都没做好**：
既重复了仓内资产，又让"演化"这件事淹没在自研滤波器里。
⇒ 本模块只做**搜索**：提案 → 约束门 → 执行打分 → 选择 → 出白盒产物。

### 2.2 与 `rf_workflow`（242）的划界

| | rf_workflow (242) | **rf_evolve (246)** |
|---|---|---|
| 输入 | 一份规格 | 一个**受限编辑面** + 一个既有算法 |
| 动作 | **单次生成**一个仿真脚本 | **多候选演化搜索** |
| 读数 | PHY 指标（ToA/能量/链路预算），由 `lora_phy` 算 | 执行打分（S/N 提升），由 `rf_brain` 算 |
| 产物 | 仿真脚本 + 结果 | **白盒算法**（可脱离 harness 运行） |

不共用代码、不重叠功能。

### 2.3 约束为什么要**分两段**（本单最有工程价值的一处）

`rf_brain` 的 `adaptive_notch` 是**逐样本 Python 循环** —— 陷波是整条链最贵的一环，
而检测只是一次 `np.fft`。所以约束门**先在便宜阶段拦**：

- **A 段（参数级，O(1)）**：LMS 稳定上界 `μ < 1/(N·λ_max)`、显著度下限（噪声底起伏 ~5.6 dB）；
- **B 段（检测级，1 次 FFT，不跑陷波）**：检出数上限（默认 12）、总陷波带宽占比上限（默认 50%）。

被拦的典型是 `prominence_db=8`：它把**噪声峰**当干扰 —— 实测检出 **161~170** 个"干扰"，
若照单全收逐个陷波，S/N 会掉到 **−92 ~ −99 dB**（灾难）且算力随时延线性爆掉。
**B 段用一次 FFT 就把它拦在陷波之前** —— 这就是那 3,002,368 次样本运算的来源。

### 2.4 LLM 提案**不是必由之路**（刻意）

SeisEvo 的搜索由 LLM 多智能体驱动。但本仓 CI / 离线环境**不保证**有 API key；
若把 LLM 做成必由之路，这个模块在没 key 的机器上**无法被验证** —— 只能演示不能回归。
⇒ 默认 `proposal="rules"`（确定性、同 seed 逐位可复现），`proposal="llm"` 为可选旁路，
不可用时**不静默降级**（写进 `notes` 与 `proposal_mode`）。

### 2.5 白盒产物必须是**真货**

SeisEvo 明确：输出「不是 agent 系统也不是神经网络，而是**推理期不需要它们**的独立白盒算法」。
⇒ 本单用三条硬判据（都进了测试）：
① 能在全新命名空间 `exec` 且 AST 上**不 import 本仓**；
② 清洗信号与 `rf_brain.mitigate_rfi` **`np.array_equal` 为真**；
③ S/N 提升与 harness 报告值差 < 1e-3 dB（报告值 round 到 4 位）。

---

## §3 · 实现

| 文件 | 作用 |
|---|---|
| `mcpserver/rf_evolve/editspace.py` | **受限编辑面**：4 个可编辑参数（各带 `why`/`affects`）+ **显式冻结组件清单**；`canonical()` 拒绝越界/未声明/缺参 |
| `mcpserver/rf_evolve/constraints.py` | **约束门**：A 段参数级 / B 段检测级；每条违规带 `rationale` + `source`；`saved_notch_ops` 记省下的算力 |
| `mcpserver/rf_evolve/candidate.py` | 候选表示（参数 + **出处** + 否决记录 + 读数） |
| `mcpserver/rf_evolve/proposers.py` | `RulesProposer`（网格扫描 → 单参数邻域扰动；网格按 seed **打乱**）与可选 `LLMProposer` |
| `mcpserver/rf_evolve/scorer.py` | 3 个确定性场景 + 真跑既有实现打分（均值 + **最差场景**） |
| `mcpserver/rf_evolve/evolve.py` | 演化主循环：全轨迹 + 门统计 + 时间预算 |
| `mcpserver/rf_evolve/codegen.py` | **白盒产物**生成（自包含、只依赖 numpy、带出处） |
| `mcpserver/rf_evolve/server.py` | `RfEvolveBridge`（9 工具）+ CLI + `doctor` 边界自述 |
| `mcpserver/rf_evolve/{agent-manifest.json,README.md,requirements.txt}` | 注册 / 文档 / 依赖 |
| `mcpserver/rf_evolve/sandbox/rfe-20261016-rfi-mitigation/` | 9 份真实运行证据（含白盒产物本体 + 其独立自检） |
| `tests/test_rf_evolve.py` | **55 用例**（七层） |
| `docs/integration-graph/rf_evolve.txt` | 依赖图（注册链 / 内部依赖 / **三处划界** / 数据流 / 产物依赖） |

---

## §4 · 验证

### 4.1 测试（55 用例，全绿）

| 层 | 关键断言 |
|---|---|
| 编辑面 | 越界/未声明/缺参必须报错；**每个参数都必须有 why/affects**；**网格每一点都必须过 `canonical`** |
| 约束门 | μ 上界 `= 1/(2·P_x) = 0.25`（数学来源，非拍脑袋）；**A 段否决时用会抛异常的 detect 证明"一次信号运算都没做"**；B 段否决时**只跑了 1 次 FFT**；灾难候选在真实信号上被拦 |
| 评分器 | 场景同 seed 逐位可复现；`min_db ≤ mean_db`；fitness 主键/次键顺序 |
| 提案器 | 网格**按批次恰好覆盖全部 504 点**；**两批不重叠**（游标回归）；**同 seed 同顺序、异 seed 异顺序**；未知 mode 报错；LLM 不可用时给理由 |
| 演化 | 优于默认（**均值与最差都更好**）；`proposed = A否 + B否 + scored`；被否者**不得有读数**；同 seed 可复现；时间预算生效 |
| 白盒产物 | 语法过；**AST 无本仓 import**；`PARAMS` == 最优；**清洗信号逐位相同**；读数差 < 1e-3 dB；**真跑 `__main__` 自检**；写盘强制 LF |
| 契约 | manifest ↔ `_TOOLS` **逐项相等**；entryPoint 真能解析到带 `handle_handoff` 的类；三种错误路径；CLI 冒烟 |

### 4.2 修掉的真 bug（都在实现期被测试抓出）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 产物一跑就 `NameError: name 'json' is not defined` | 模板的 `__main__` 自检用了 `json` 却没 import；**只 exec 不真跑测不到** | 模板补 `import json` + **新增「真跑自检」测试** |
| 2 | 产物 `exec` 报 `NameError: name 'null' is not defined` | 用 `json.dumps` 生成 **Python** 源码 ⇒ `null/true/false` 非法 | 改用 `pprint.pformat` |
| 3 | 网格 504 点变成 756 点、`adaptive=None` 混入 | bool 参数无 low/high，走了通用池 `[default, low, high]` | bool 单独 `[False, True]` + 去重；**加不变量测试** |
| 4 | 扰动器给出 `adaptive=0.0` 且被判"没改动" | 走数值分支 `float(False)*2`，而 `0.0 == False` 为真 | bool 直接取反 |
| 5 | 第二批候选**重复第一批** | 首次调用单开分支但没推进游标 | 统一游标；**加"两批不重叠"回归测试** |
| 6 | 小预算下搜索覆盖不到有希望的区域 | `itertools.product` 字典序 ⇒ 前几批全落在第一个参数的最低档（恰是灾难值） | 网格按 seed **打乱**；**加覆盖不变量测试** |
| 7 | 文档写的「先铺网格再扰动」实际不生效 | `evolve()` 首代就传了带分数的 best ⇒ 直接进扰动 | 首代传 `best=None` |

> 这七条里，**五条是"测试先写对了断言"才暴露的**（不变量式断言 > "跑通就行"）。

### 4.3 真跑证据

`sandbox/rfe-20261016-rfi-mitigation/` 9 份，命令写在同目录 README 可复跑。抽样：

```
# 基线（仓库默认参数）
three_strong_tones +11.5748 ｜ one_strong_two_weak +5.3269 ｜ interferer_inside_band +3.3958
# 演化所得
three_strong_tones +19.5325 ｜ one_strong_two_weak +16.8718 ｜ interferer_inside_band +12.9993
# 灾难候选被拦
gate_probe_rejected_catastrophic.json: passed=false, stage=B, detected=161, saved_notch_ops=1,157,584
# 白盒产物独立自检
{"detected": 1, "improvement_db": 20.1718}
```

---

## §5 · 未落地（明确列出）

1. **场景是合成的** —— LoRa 式 chirp + 单音干扰，不是实测空口数据；结论限于该场景集。
   要升级：接真实 SDR 采集（`rf_brain/sdrtrunk_bridge` 等）做留出验证。
2. **LLM 提案未在真 key 下跑过** —— 本机无凭据，只验证了「不可用时明确降级」这条路径。
3. **约束阈值是本仓工程口径**（检出数上限 12、总陷波带宽 ≤ 50%），不是标准规范值。
4. **只登记了 1 个编辑面** —— 框架支持多编辑面（`spaces()` 是注册表），但本单只落了 RFI 抑制这一个。
5. **不做硬件在环 / 真实发射 / Gerber**（与 245 同边界）。

---

## §6 · 复现

```bash
PY=.venv/Scripts/python.exe
$PY -m mcpserver.rf_evolve.server doctor
$PY -m mcpserver.rf_evolve.server evolve --generations 4 --batch 6
$PY -m mcpserver.rf_evolve.server whitebox --out /tmp/wb.py && $PY /tmp/wb.py
$PY -m pytest tests/test_rf_evolve.py -q          # 55 passed
```
