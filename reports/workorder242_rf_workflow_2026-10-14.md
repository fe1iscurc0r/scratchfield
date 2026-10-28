# 工单242 交付报告 · Prompt→RF 工程工作流 · SDR 工具集

> 漏斗 2.0 轻量猎手第 2 单 ｜ 仓库 `fe1iscurc0r/scratchpad` ｜ 出单：沈遥 ｜ 交付：2026-10-14
> 素材：arXiv `2608.31006`《From Prompt to Prototype: Towards a Frontier LLM Driven RF Engineering Workflow》
> 交付基线：fork 自 `main` `dba750ed72`（工单241 合并点）

## §0 一句话

在 `mcpserver/rf_workflow/` 落了一条**可跑的** prompt→RF 脚本→执行→解释回路：三条接口
（`start_workflow` / `step` / `explain`）+ 两条只读，真跑了一个 LoRa 433 MHz / SF7 / 14 dBm 的
发射功率估算 PoC，四件套 + `result.json` 入库，**19 个文件全部新增，未修改任何既有文件**。

## §1 交付物清单（19 文件）

| # | 路径 | 字节 | 说明 |
| --- | --- | --- | --- |
| 1 | `mcpserver/rf_workflow/__init__.py` | 1015 | 包入口，导出 `RfWorkflowBridge` |
| 2 | `mcpserver/rf_workflow/server.py` | 16767 | MCP 入口 + 三接口 + 两条只读 + CLI |
| 3 | `mcpserver/rf_workflow/prompt_to_script.py` | 15248 | goal→规格→脚本文本；沙箱 vendor；LLM 补参（可选） |
| 4 | `mcpserver/rf_workflow/sim_runner.py` | 9628 | 沙箱根/id 收敛、受限子进程执行、指标解析 |
| 5 | `mcpserver/rf_workflow/explainer.py` | 13694 | 规则观测 + 下一步建议 + 候选变体 + `explanation.md` |
| 6 | `mcpserver/rf_workflow/lora_phy.py` | 27799 | **真值源**：ToA 公式/链路预算/chirp 合成+纯标准库 FFT |
| 7 | `mcpserver/rf_workflow/agent-manifest.json` | 5834 | 5 条 invocationCommands（Format A） |
| 8 | `mcpserver/rf_workflow/README.md` | 6908 | 结构/接口/实测表/口径/三处偏差/四个踩坑 |
| 9 | `mcpserver/rf_workflow/requirements.txt` | 1205 | 声明**无第三方运行时依赖**（numpy 为可选增强） |
| 10-16 | `mcpserver/rf_workflow/sandbox/rfw-20261014-lora433-sf7/` | 49633 | PoC 四件套 + `result.json` + `workflow.json` + vendor `lora_phy.py` |
| 17 | `docs/integration-graph/rf_workflow.txt` | 7099 | 任务三 ASCII 依赖图（7 节） |
| 18 | `tests/test_rf_workflow.py` | 21466 | 33 用例（happy path + 边界 + 契约 + 交付纪律） |

`docs/integration-graph/` 目录本单**新建**（工单声明的路径，全树此前 0 命中）。

## §2 路径对账（工单 §1/§2 写的路径 vs 本仓实况）

| 工单写的 | 本仓实测（main `dba750ed72`，全树 22542 blob） | 处理 |
| --- | --- | --- |
| `mcpserver/sdr/` | ❌ 0 命中 | 不引；落点改 `mcpserver/rf_workflow/` |
| `core/sdr_signal/` | ❌ 0 命中（`core/` 整个目录在仓库根不存在） | 不引 |
| `core/rf_brain/` | ❌ 0 命中（同上） | 不引 |
| `mcpserver/kicad-mcp/` | ❌ 0 命中（本仓子模块用下划线命名） | 不引 |
| `mcpserver/rf_workflow/`（§2 指定落点） | ❌ 0 命中 ⇒ **待创建** | ✅ 按此创建 |
| `docs/integration-graph/`（§3 指定） | ❌ 0 命中 ⇒ **待创建** | ✅ 按此创建 |
| `tests/test_rf_workflow.py` | ❌ 0 命中 ⇒ **待创建** | ✅ 按此创建 |
| `mcpserver/rf_brain/` | ✅ 244 文件（含 `dcp/` 4 文件） | 只做参数口径对齐，不 import |
| `mcpserver/antenna_sim/` | ✅ 9 文件 | **结构先例**（sim 纪律照抄语义） |
| `firmware/dcp_lora/` | ✅ 4 文件（`sx1278_lora.cpp` 等） | PoC 起点参数来源 |
| `mcpserver/llm_gateway/` | ✅ 2 文件（`anthropic_compat.py`） | LLM 通路惰性导入 |

⇒ 这是本仓第 **8** 次「工单写的路径不是本仓路径」；同 241，`core/` 目录整体不存在。
落点全部按工单 §2/§3 **自己声明的仓内路径**执行，工单 §1 提到的既有模块**一个都没引用**。

## §3 任务落地

### 任务一（P0）骨架 ✅
`__init__.py / server.py / prompt_to_script.py / sim_runner.py / explainer.py` 五件齐；
额外 `lora_phy.py` 作为**唯一真值源**（解释见 §7），`agent-manifest.json` 供 MCP 注册。

三条接口（语义与工单一致，参数名一致）：

| 接口 | 返回 |
| --- | --- |
| `start_workflow(goal, rf_lib)` | `workflow_id` + 解析出的 spec + `prompt.md` |
| `step(workflow_id, prompt)` | `script` / `log` / `result` / `metrics` |
| `explain(workflow_id, output_id)` | `explanation` + `next_step_suggestion` + `candidates` |
| `workflow_status` / `list_workflows`（额外只读） | 状态 / 最近工作流列表 |

### 任务二（P0）真实 PoC ✅

```bash
python -m mcpserver.rf_workflow.server run --workflow-id rfw-20261014-lora433-sf7 \
  --goal "设计一个 LoRa chirp 在 433 MHz 的发射功率估算器，给定扩频因子 7，输出功率 14 dBm"
```

`mcpserver/rf_workflow/sandbox/rfw-20261014-lora433-sf7/` 实测（**stdlib，无任何第三方依赖**）：

| 量 | 实算值 | 口径 |
| --- | --- | --- |
| 符号时长 / chirp 斜率 | 1.024 ms / 122.0703 MHz/s | `Tsym = 2^SF/BW`；`k = BW/Tsym = BW²/2^SF` |
| 载荷符号数 / ToA | 38 / **51.456 ms** | Semtech AN1200.13（SF7 BW125 CR4/5，16 B，CRC 开，显式头） |
| 标称 / 含开销速率 | 5468.75 / 2487.56 bps | 后者 = payload bit / ToA ⇒ 45.487% |
| 每符号 / 每比特能量 | 25.72 / 10.10 µJ | `P·Tsym` / `P·ToA/(8·PL)` |
| 灵敏度（BW125） | −123 dBm | SX1276/77/78 手册典型值 |
| 自由空间路损 @1 km | 85.18 dB；链路余量 51.82 dB | FSPL |
| 自由空间距离上限 | 389.95 km | **理论上限**，不含地物/多径/衰落 |
| 占用带宽 −6 dB / 99% | 122.07 kHz（97.66%·BW）/ 133.79 kHz | 合成 chirp 双边 FFT |
| 占空比 | 0.0858%（限值 10%） | 周期 60 s |
| ERP | **11.85 dBm（限值 10）⇒ 超限** | `ERP = EIRP − 2.15 dB`；传导上限 12.15 dBm |
| 频点 | 433.00 MHz **不在** 433.05–434.79 子带内 | 固件取的是子带中心 433.92 MHz |

解释结论（`mode="rules"`）先指出 ERP 超限与频点越界，再给合规化后余量 49.97 dB 仍充裕的结论，
最后要求用实测 RSSI 替换自由空间路损。**没有编造"带宽利用率 87%""还差 4 dB"这两个素材示例数字**
（见 §6 偏差 2）。

### 任务三（P1）耦合点 + ASCII 依赖图 ✅

依赖图：`docs/integration-graph/rf_workflow.txt`（7 节：注册路由链 / 模块内部 / 沙箱运行期 /
LLM 通路 / 参数口径对齐 / 不存在路径 / 产物口径）。

**结论：本单未修改任何既有文件。** 原因（已实测，非推断）：

```
mcpserver/mcp_registry.py::scan_and_register_mcp_agents("mcpserver")
  → d.glob("**/agent-manifest.json")        ← 自动发现，无登记表
  → verify_entrypoint("mcpserver." 前缀白名单 + 类须有 handle_handoff)
  → MCPManager.unified_call 路由
```

实跑注册链（真实仓库配置下）：

```
registered count: 55
rf_workflow in registered: True
verify_entrypoint: True (ok)
instantiated: RfWorkflowBridge  has handle_handoff: True
tools: ['start_workflow', 'step', 'explain', 'workflow_status', 'list_workflows']
```

唯一的**代码级耦合**是 import `mcpserver/llm_gateway/anthropic_compat.py`（惰性、只读）；
`rf_brain/dcp`、`firmware/dcp_lora`、`antenna_sim` 三处只做**参数/纪律口径对齐**（虚线），
不改其接口。工单「只改主调用路径不动现有模块内部接口」在此表现为**零改动**。

## §4 验收逐条对账

| # | 验收项 | 结果 |
| --- | --- | --- |
| 1 | `pytest tests/test_rf_workflow.py -q` 全绿 | ✅ **33 passed**（真实仓库 pyproject + conftest 配置下） |
| 2 | 目录完整（7 项 + `__init__.py`） | ✅ 9 文件（含 `lora_phy.py` / `agent-manifest.json`） |
| 3 | sandbox 可见 prompt/script/log/explanation 四件套 | ✅ 7 文件（四件套 + `result.json` + `workflow.json` + vendor） |
| 4 | 模块依赖图 ASCII 落盘 | ✅ `docs/integration-graph/rf_workflow.txt` |
| 5 | PR 描述复述 §0 六个 arXiv 复查 | ✅ §5（6/6 HTTP 200） |
| 6 | 不碰 `mcp_assembly` / `mcp/services` 路由健康检查、`core/` stdlib 强约束、`coupled/` 桌宠 | ✅ 一文件未改（§3） |

## §5 §0 六个 arXiv 链接复查（2026-10-14 实测，直连 `arxiv.org/abs/<pid>`）

| pid | 工单标注 | HTTP | 实测标题（截断） | abstract 字符数 |
| --- | --- | --- | --- | --- |
| `2608.31006` | 主体 VERY_HIGH | **200** | From Prompt to Prototype: Towards a Frontier LLM Driven RF Engi… | 719 |
| `2608.19084` | LOW 噪声项 | **200** | Cluster Assignments in Soft Targets Shape Speech Representation… | 1211 |
| `2608.21009` | LOW | **200** | Dorsal Hand Images for Immersive (XR) and Privacy-preserving Ag… | 1619 |
| `2608.21231` | MEDIUM | **200** | Pattern Multiplication Underestimates the Sidelobe Level of a P… | 1234 |
| `2608.25895` | MEDIUM | **200** | Room-temperature graphene sub-terahertz detector integrated on … | 1423 |
| `2608.28188` | LOW | **200** | Beyond Flat Netlist: Hierarchical Graph Representation Learning… | 1117 |

复查方法（241 定式）：官方 API `export.arxiv.org/api/query` 会 **429**，改直连 abs 页解析
`<h1 class="title>` 与 `<blockquote class="abstract>`；脚本 `_w242-2026-10-14/probe/check_arxiv_242.py`，
原始结果 `arxiv_links_242.json`。**6/6 全 200，标题与工单标注的六项主题一一对应**。

## §6 与工单叙述的偏差（如实记录）

1. **路径偏差**：见 §2（`core/` 不存在等，第 8 次）。
2. **素材示例数字不复现**：工单 §2 任务二写"输出'仿真功率 + 频谱占用' → LLM 解释'带宽利用率 87%，
   距离实测信噪比还差约 4 dB'"。这两个数是**素材里的示例叙述，不是本仓参数下的实算结果**。
   本模块一律实算：`bandwidth_utilisation_pct` = **97.656%**（−6 dB 带宽 / BW），
   链路余量 = **51.82 dB**（@1 km 自由空间），"还差 4 dB" 无从复现（自由空间假设下余量远超 0）。
   报告与 README 均以实算为准并显式说明该差异。
3. **落点补件**：工单 §2 任务一只列了 5 个文件，本单补了 `lora_phy.py`（真值源，见 §7）
   与 `agent-manifest.json`（本仓 MCP agent 注册**必需**，缺失则 `scan_and_register_mcp_agents`
   扫不到）。二者都不是可选装饰。
4. **`requirements.txt` 内容**：工单只要求"有这个文件"。本单写成**声明式**（无第三方运行时依赖 +
   numpy 为可选增强 + 未来引入真实 RF 库时的登记约定），而不是塞一个空文件或复制根 requirements。

## §7 设计取舍：为什么要有 `lora_phy.py`

「生成的脚本要能独立跑」与「物理量只能有一份实现」是冲突的：

- 若把公式抄进生成脚本 ⇒ 仓内与沙箱两份实现，**必然漂移**；
- 若让脚本 import 仓内模块 ⇒ 得把仓库绝对路径写进脚本 ⇒ 违反「不硬编码本机路径」，
  且沙箱不再可移植。

取舍：**沙箱按字节 vendor `lora_phy.py` 到工作流目录**，脚本 `from lora_phy import …`（同目录）。
两个回归断言把这个不变量钉住：

- `test_generate_writes_self_contained_sandbox`：`vendored.read_bytes() == Path(lora_phy.__file__).read_bytes()`
- `test_full_workflow_poc_produces_four_artifacts`：沙箱里的 `lora_phy.py` 同样字节等同

另有 `test_workflow_metrics_agree_with_in_repo_computation`：把子进程脚本产出的 40+ 个指标
逐项与仓内 `compute_metrics` 比对（浮点 `rel=1e-9`），锁死"脚本 = 真值源"。

## §8 质量与回归

| 检查 | 结果 |
| --- | --- |
| ruff（仓库 `pyproject.toml` 配置，含 `E/F/I/UP/N/SIM`） | ✅ `All checks passed!`（含生成的沙箱 `script.py`） |
| `pytest tests/test_rf_workflow.py`（真实仓库配置） | ✅ **33 passed** |
| 241 治理套件 + 本单（同场共存） | ✅ **87 passed**（`test_agent_governance{,_hook}.py` 54 + 本单 33） |
| 229 回归 `tests/test_peak_switch.py` | ✅ **23 passed**（与 229/241 基线一致） |
| 同族先例 `tests/test_antenna_sim.py` | ✅ **14 passed**（与其 README 基线一致） |
| MCP 注册链实跑 | ✅ 55 agent 注册、`verify_entrypoint` True、可实例化、5 工具 |
| 行尾 | ✅ 19 文件全 LF（`crlf == 0`），沙箱产物亦全 LF（含子进程 `log.txt` 归一化） |
| 绝对路径扫描 | ✅ 交付物 0 命中（`workflow.json` 只存相对文件名） |
| 既有文件改动 | ✅ **0**（19 文件全为新增） |

**回归面说明**：本单不修改任何既有文件 ⇒ 无既有行为回归面；上表四条既有套件是为证明
「新增模块与既有注册表/路由/同族模块共存无扰」而跑的。

## §9 未落地 / 需沈遥侧接手

1. **LLM 通路未在真环境验证**：`llm_refine_spec` / `llm_narrate` 只在「无 key ⇒ 返回 None ⇒
   `mode="rules"`」这条分支上实测过。要走通 `mode="llm"`，需在云服配 `ANTHROPIC_API_KEY` 后复跑；
   **本报告不声称 LLM 通路已验证**。
2. **真实 RF 库未引入**：工单提到的 "rpsreal/radioutils" 在本仓与 PyPI 均未确认存在，本单用
   纯标准库替代，`requirements.txt` 里留了引入真实 RF 库时的登记约定。
3. **频谱精度口径**：占用带宽来自合成 chirp 的双边 FFT（理论占用 = BW）；精确 OBW 需按
   ITU-R SM.443 用真实仪表测 —— 本模块不声称替代仪表。
4. **法规限值需复核**：占空比 10% 与 ERP 10 dBm 按 433.05–434.79 MHz 子带填写，落地地区/天线型式
   不同需重核；`in_ism_433` 只做频点是否在带内的机械判断。
5. **参数扫描未实现**：`explainer` 已给出 SF/BW/功率三个候选变体的**实算预测**，但"网格扫描 +
   批量落盘"未做（工单未要求）。

## §10 数据快照口径

- 基线 main tip：`dba750ed72`（工单241 合并点）。全树 22542 blob。
- 路径存在性、`antenna_sim` 9 文件、`rf_brain` 244 文件等计数均在该快照上实测。
- arXiv 复查与全部测试执行时间：2026-10-14。
- 沙箱产物 `rfw-20261014-lora433-sf7/workflow.json` 内的 `created_at/updated_at` 是
  生成时刻的真实时间戳（非模拟值），`duration_s` 是那次执行的真实耗时。
