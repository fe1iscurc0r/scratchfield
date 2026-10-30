# Prompt→RF 工程工作流（工单242 · 漏斗 2.0 轻量猎手第 2 单）

把「自然语言需求 → 可跑 RF 仿真脚本 → 受限执行 → 结果解释 → 下一轮建议」做成一条
可跑的 MCP 工作流。素材：arXiv `2608.31006`《From Prompt to Prototype: Towards a
Frontier LLM Driven RF Engineering Workflow》。

## 结构

```
mcpserver/rf_workflow/
├── server.py            MCP 入口 RfWorkflowBridge（start_workflow / step / explain / workflow_status / list_workflows）
├── prompt_to_script.py  goal → 规格 → 脚本（模板 + 沙箱 vendor；LLM 补参为可选增强）
├── sim_runner.py        沙箱根与 id 收敛、受限子进程执行、指标解析
├── explainer.py         规则观测 + 下一步建议 + 候选变体（LLM 只改写叙述，不产数字）
├── lora_phy.py          **真值源**：Semtech ToA 公式 / 链路预算 / chirp 合成 + 纯标准库 FFT
├── agent-manifest.json  5 条 invocationCommands（供 LLM 调用；mcp_registry 自动登记）
├── requirements.txt     无第三方运行时依赖（numpy 为可选增强）
└── sandbox/<workflow_id>/   真实 PoC 产物（prompt.md / script.py / log.txt / explanation.md / result.json）
```

## 三条接口（工单242 §2 指定）

| 接口 | 入参 | 出参 |
| --- | --- | --- |
| `start_workflow` | `goal`, `rf_lib`, `workflow_id?` | `workflow_id` + 解析出的 spec + `prompt.md` |
| `step` | `workflow_id`, `prompt?`, `rf_lib?`, `timeout_s?` | `script` / `log` / `result` / `metrics` |
| `explain` | `workflow_id`, `output_id?`, `allow_llm?` | `explanation` + `next_step_suggestion` + `candidates` + `explanation.md` |

外加两条只读：`workflow_status` / `list_workflows`。

## 已落地的真实 PoC

```bash
python -m mcpserver.rf_workflow.server run \
  --workflow-id rfw-20261014-lora433-sf7 \
  --goal "设计一个 LoRa chirp 在 433 MHz 的发射功率估算器，给定扩频因子 7，输出功率 14 dBm"
```

产物在 `sandbox/rfw-20261014-lora433-sf7/`（四件套 + `result.json` + `workflow.json`）。
实测（`stdlib`，无任何第三方依赖）：

| 量 | 值 | 口径 |
| --- | --- | --- |
| 符号时长 / chirp 斜率 | 1.024 ms / 122.0703 MHz/s | `Tsym = 2^SF/BW`，`k = BW/Tsym` |
| 载荷符号数 / 空中时间 | 38 / **51.456 ms** | Semtech AN1200.13（SF7 BW125 CR4/5，16 B，CRC 开，显式头） |
| 标称 / 含开销速率 | 5468.75 / 2487.56 bps | `Rb = SF·BW/2^SF·4/(4+CR)`；后者按 payload bit / ToA |
| 每符号 / 每比特能量 | 25.72 / 10.10 µJ | `P·Tsym` / `P·ToA/(8·PL)`，P = 14 dBm |
| 灵敏度（BW125） | −123 dBm | SX1276/77/78 手册 BW=125 kHz 典型值 |
| 自由空间路损 @1 km | 85.18 dB | `20log10(d)+20log10(f)−147.55` |
| 链路余量 / 距离上限 | 51.82 dB / 389.95 km | 后者是**自由空间理论上限**，不含地物/多径 |
| 占用带宽 −6 dB / 99% | 122.07 kHz（97.66%·BW）/ 133.79 kHz | 合成 chirp 的双边 FFT |
| ERP | 11.85 dBm（限值 10） | `ERP = EIRP − 2.15 dB`；传导上限 12.15 dBm |

解释结论由**规则**产出（`mode="rules"`）：先指出 ERP 超限与频点不在 433.05–434.79 子带内，
再给出合规化后余量（49.97 dB）仍充裕的结论，最后要求用实测 RSSI 替换自由空间路损。

## 数值口径（都写在产物里，不只在文档）

- **灵敏度/SNR**：手册表 + `10log10(BW/125k)` 热噪声缩放，属**工程近似**（不含实现损耗）。
- **链路预算**：纯自由空间（FSPL）。"距离上限"是理论值，**不能当实测通信距离用**。
- **法规限值**：占空比 ≤10%、ERP ≤10 dBm 按 433.05–434.79 MHz 子带（ERC/REC 70-03 Annex 1 /
  MIIT 微功率短距离目录）填写，**部署前须按落地地区复核**；`in_ism_433` 直接给出频点是否在带内。
- **占用带宽**：合成 chirp 的双边 FFT。**默认不加窗**——chirp 是扫频信号，功率谱密度按停留时间
  加权，加 Hann 会按窗形压掉扫频两端（实测把 −6 dB 带宽从 0.98·BW 压到 0.50·BW）。
  99% 能量带宽含矩形截断的谱泄漏（理论占用 = BW）；精确 OBW 应按 ITU-R SM.443 用仪表测。
- **`bit_efficiency_pct` ≠ 频谱效率**：前者是 payload bit/ToA 相对标称速率，后者是
  `airtime_bitrate/bw`（SF7 BW125 下约 0.0199 bps/Hz）。

## 与工单叙述的三处偏差（如实记录）

1. 工单 §1 提到的 `mcpserver/sdr/`、`core/sdr_signal/`、`core/rf_brain/` **在本仓都不存在**
   （`core/` 整个目录在仓库根不存在）。真实存在的同族资产是 `mcpserver/rf_brain/`（244 文件，
   含 `dcp/`）、`mcpserver/antenna_sim/`（9 文件，本单的结构先例）与 `firmware/dcp_lora/`。
   ⇒ 落点按工单语义规范到 `mcpserver/rf_workflow/`（工单 §2 指定的正确路径），**不引不存在的模块**。
2. 工单 §2 任务二写的"带宽利用率 87%、距离实测信噪比还差约 4 dB"是**素材里的示例叙述**，
   本模块不照抄：`bandwidth_utilisation_pct` 由 FFT 实算得 **97.66%**，链路余量也按实际参数算。
   示例数字与实算不符时，以实算为准并在此说明。
3. 工单要求 `server.py` 作"MCP 入口"。本仓 MCP agent 的注册契约是
   `agent-manifest.json` 的 `entryPoint.{module,class}` + 类方法 `handle_handoff`
   （见 `mcpserver/mcp_registry.py::_resolve_entrypoint`），所以 `server.py` 同时承载
   `RfWorkflowBridge`，`entryPoint` 指过去即可，**无需改任何既有文件**。

## 踩坑记录（都在代码注释里留了锚）

1. **规格字面量不能直接 `json.dumps`**：生成脚本里会出现 `null/true/false` 三个 Python 里不存在的
   名字，脚本 `NameError: name 'null' is not defined`。改成 `repr` 递归渲染（`spec_literal`）。
2. **FFT 占用带宽必须用双边谱**：LoRa 基带 chirp 跨越 `±BW/2`，只取正频率半边会把占用带宽
   算成实际值的一半（首版实测 53%·BW，修正后 97.66%·BW）。
3. **`Path.write_text` 在 Windows 默认把 `\n` 翻成 `\r\n`**：所有产物写入都显式
   `newline="\n"`，回归用例断言 crlf==0。
4. **沙箱状态文件不能存绝对路径**：`workflow.json` 会随沙箱入库，故一律只存**相对文件名**，
   绝对路径在 `workflow_status` 返回时按当前沙箱根解析。

## 沙箱与安全

- 沙箱根默认 `mcpserver/rf_workflow/sandbox/`，`RF_WORKFLOW_SANDBOX` 可覆盖（测试即走这条）。
- `workflow_id` 只允许 `[A-Za-z0-9_-]{1,64}`，一次只跑一步（串行，`busy` 拒绝并发）；
  子进程 argv 列表直执、无 shell、`stdin=DEVNULL`、超时 kill（默认 120 s，上限 1800 s）。
- 解释器取 `RF_WORKFLOW_PYTHON`，默认当前解释器。

## 测试

```bash
python -m pytest tests/test_rf_workflow.py -q
```
