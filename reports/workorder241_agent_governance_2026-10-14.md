# 工单 241 交付报告 · 多 agent 身份授权 + 运行时治理（漏斗 2.0 轻量猎手第 1 单）

> 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 日期：2026-10-14
> 基线快照：**main `d13913cf7b`**（全树 25,076 条目，`truncated=false`）· 本报告所有计数均在该快照上实测

## §0 · 一句话

把「多 agent 协作安全」从纸面文章落到代码骨架：给 scratchpad 加一套 **身份证明 / 授权令牌 / 运行时审计** 三层治理，并把它接到真正的统一派发点
（`MCPManager.unified_call`），开关默认关闭 —— **既有行为一字未改**，开启后带篡改或伪造的调用一律拦下并留审计证据。

## §1 · 交付物

| # | 文件 | 性质 | 说明 |
|---|---|---|---|
| 1 | `mcpserver/agent_governance/__init__.py` | 新增 | 包入口 + 全量 re-export |
| 2 | `mcpserver/agent_governance/errors.py` | 新增 | 稳定错误码契约（10 个） |
| 3 | `mcpserver/agent_governance/identity.py` | 新增 | HMAC-SHA256 输出签名 / 验签 |
| 4 | `mcpserver/agent_governance/authorization.py` | 新增 | 短期 token 签发 / 校验（默认 TTL 1h） |
| 5 | `mcpserver/agent_governance/audit.py` | 新增 | JSONL **append** 审计（禁 `json.dump` 一次性写） |
| 6 | `mcpserver/agent_governance/integration.py` | 新增 | 零侵入 guard + 自指式 hook 契约常量 |
| 7 | `mcpserver/agent_governance/governance.py` | 新增 | MCP agent 适配层（7 个工具） |
| 8 | `mcpserver/agent_governance/agent-manifest.json` | 新增 | Format A manifest（同族形态） |
| 9 | `mcpserver/agent_governance/README.md` | 新增 | 用法 / 契约 / **三处偏差如实说明** |
| 10 | `mcpserver/agent_governance/__main__.py` | 新增 | CLI：`demo` / `selftest` / `audit-tail` / `resign` |
| 11 | `tools/agent_rekey.sh` | 新增（100755） | 峰谷切换后重签挂起任务 |
| 12 | `tests/test_agent_governance.py` | 新增 | 三件套 + 场景 A/B/C 共 38 用例 |
| 13 | `tests/test_agent_governance_hook.py` | 新增 | 接线层 16 用例 |
| 14 | `mcpserver/mcp_manager.py` | **定点修改** | **`+32 -0`** 纯新增（helper + 调用点 3 行），无删除 |
| 15 | `tools/peak_switch.sh` | **定点修改** | `+26 −1`（仅 usage 行改写 + 追加 re-key 段） |
| 16 | `reports/workorder241_agent_governance_2026-10-14.md` | 新增 | 本报告 |

实测计数：`pytest tests/test_agent_governance*.py -q` → **54 passed**（含参数化展开）；
`pytest tests/test_agent_governance*.py tests/test_peak_switch.py -q` → **77 passed**。

## §2 · 路径对账表（工单写的 vs 本仓实测）

这是本仓**第七次**遇到「工单写的路径不是本仓路径」。本单尤其严重：**整个 `core/` 目录在本仓不存在**。

| 工单原文 | 本仓实测（main `d13913cf7b`） | 处置 |
|---|---|---|
| `core/agent_governance/` | ❌ **无 `core/`**（全树 `core/` 前缀 0 命中） | 规范化落到 `mcpserver/agent_governance/`，与既有 20+ 个 `mcpserver/agent_*` 同族并列 |
| `mcpserver/llm_gateway/dispatcher.py` | ❌ 不存在（该目录只有 `__init__.py` + `anthropic_compat.py`） | hook 落到真正的统一派发点 `mcpserver/mcp_manager.py::MCPManager.unified_call` |
| `~/.hermes/audit/agent_calls.jsonl` | ❌ 本机无 `~/.hermes` | 默认值保持工单口径；本地 e2e 用 `AGENT_AUDIT_DIR` 覆盖 |
| `tools/peak_switch.sh` | ✅ **存在**（工单此条命中） | 直接改 |
| `tests/test_agent_governance*.py` | ✅ 路径口径与仓内 `testpaths=["tests"]` 一致 | 落在根 `tests/`（同时也吃到 `per-file-ignores`） |

依赖的既有同族模块（**先搜先例**，全部先读真字节再动手）：

* `mcpserver/agent_signing/agent_signing.py` —— 提供了 agent 契约模板：模块级 `handle_handoff(task) -> JSON str` + 类方法委托 + `agent-manifest.json` Format A（`entryPoint: {module, class}`）。
* `mcpserver/trace_audit/{schema,audit}.py` —— 提供了时间戳口径（`datetime.fromisoformat` 可解析）+ 事件字段惯例。
* `mcpserver/scope.py` —— 提供了「展示层 + 执行层双层校验」与 fail-open 的对照设计（本层刻意反其道，见下）。

## §3 · 三任务落地

### 任务一（P0）：身份-授权骨架（核心）✅

* **身份层** `identity.py`：签名把 `agent_id` + `provider` + `model` + `timestamp` + `content_sha256` 绑成一份 canonical JSON 后做 HMAC-SHA256。所以「谁产的 / 用哪个模型产的 / 内容是什么」三者**不可分离** —— 改任一项验签必失败。
* **授权层** `authorization.py`：`v1.<b64url(payload)>.<b64url(hmac)>`，默认 TTL 3600s，逐 token 可覆写；payload 含 `provider` 与 `key_id`（与密钥绑定）。
* **审计层** `audit.py`：`open(..., "a", newline="\n")` + `write(line + "\n")` + `flush()`。**代码里不存在 `json.dump(`**（有静态回归用例守着）。
* **零业务侵入**：既有文件只动 `mcp_manager.py`，且是 `+32 -0`（纯新增）。`unified_call` 的既有分支（鉴权守卫 / 熔断 / 冷表转热 / 指标 / 错误处理）**一行未改**。

### 任务二（P0）：典型场景验证（3 个）✅

| 场景 | 要求 | 实测 |
|---|---|---|
| A | 授权链 A→B→C→A 闭环签名往返，每段可验签 | ✅ `closed_loop=True`，**4 段 hop 全部独立验签通过**（`agent-A → agent-A → agent-B → agent-C`） |
| B | 过期 token（ttl=0）被拒，给出明确错误码 | ✅ 拒绝，`code=GOV_TOKEN_EXPIRED` |
| C | 伪造 agent ID（随机 key）被拒，审计记 `unauthorized_attempt` | ✅ 拒绝，`code=GOV_BAD_SIGNATURE`；审计里 `unauthorized_attempt` 计 **2** 条（B + C 各一条） |

CLI 实证输出（`python -m mcpserver.agent_governance selftest`）：

```
[A] 闭环=True 段数=4（每段独立验签通过）
[B] 过期令牌被拒=True code=GOV_TOKEN_EXPIRED
[C] 伪造 agent 被拒=True code=GOV_BAD_SIGNATURE
[审计] unauthorized_attempt 条数=2
selftest: PASS
```

### 任务三（P1）：与峰谷切换配套 ✅（含一处刻意的开关化偏差）

* 新增 `tools/agent_rekey.sh`：把 `pending_tasks.jsonl` 里的挂起任务用**新 provider** 重签，原子替换（tmp + `os.replace`），逐条写 `re_sign` 审计事件（含 `from_provider → to_provider`），输出 **`re-sign count: N`**。
* `tools/peak_switch.sh` 切换后调用它，切换日志因此带上 `re-sign count` 指标。

⚠️ **偏差（如实记录）**：工单要求「切换 provider 时**必须**重新签署」。实测若做成无条件执行，会破坏 229 交付的
`tests/test_peak_switch.py`（该套 23 个用例断言 hermes 调用序列、`--dry-run` 零副作用、未知参数 exit 2）。
因此改为**显式开关**：`--rekey` 或 `AGENT_REKEY=1` 打开，**默认关闭**。关闭时本脚本对 stdout 与 hermes 调用序列零影响 ——
`tests/test_peak_switch.py` **改前 23 passed / 改后 23 passed**（见 §8）。

## §4 · 验收对账（逐条）

| 工单 §3 验收 | 结果 | 证据 |
|---|---|---|
| 1. `pytest tests/test_agent_governance*.py -q` 全绿（≥6 用例，覆盖 A/B/C + 边界） | ✅ **54 passed**（远超 6；A/B/C + 边界全覆） | 见 §8 |
| 2. 目录三件套完整（`identity.py` / `authorization.py` / `audit.py` / `__init__.py` / `README.md`） | ✅ 5 件齐（另加 `errors/integration/governance/__main__` + manifest） | §1 |
| 3. **不破坏**：`tests/` 现有用例通过数 ≥ 现基线 | ✅ 受影响的既有套件全绿 | `test_peak_switch.py` 23/23；`mcpserver/tests/test_telemetry.py` + `test_fault_inject.py` 39/39 |
| 4. **强制**：审计 log 用 `jsonl.append`，每次一行，**禁止** `json.dump` 一次性写 | ✅ 有静态回归用例 `test_audit_source_uses_append_never_json_dump` + 追加语义用例 + LF 用例 | §5 |
| 5. PR 描述里完整复述 §0 的 4 个 arXiv 链接复查表 | ✅ 见 §5 与 PR 正文 | §5 |
| 6. **不许触碰**：`mcp_assembly` / `mcp/services` 路由健康检查、`coupled/` 桌宠、`.hermes/config.yaml` | ✅ 均未触碰（`.hermes` 只读；本机根本没有该目录） | §8 |

## §5 · §0 四个 arXiv 链接复查表（实测，2026-10-14）

方法：直连 `https://arxiv.org/abs/<pid>` 取 HTML，解析 `blockquote.abstract` 后去标签、压平空白再计数（不靠肉眼、不靠摘要转述）。
原始数据落盘 `probe/arxiv_links_241.json`。

| pid | HTTP | abstract 字符数 | 摘要末句（原文摘录） | 与工单声明的标题是否一致 |
|---|---|---|---|---|
| `2609.00267`（主体 VERY_HIGH） | **200** | **1927** | "These principles are also realized in production in VotalAI's LLM Shield." | ✅ 一致：《Delegation Without Trust: An Empirical Gap Analysis of Identity, Authorization, and Runtime Governance in Multi-Agent LLM Systems》 |
| `2501.02406`（鉴伪方法支撑 HIGH） | **200** | **1347** | "Our framework provides rigorous guarantees for LLM provenance detection, with applications to content verification, institutional compliance, and misinformation mitigation." | ✅ 一致：《A Training-free Method for LLM Text Attribution》（工单描述「无训练 LLM 文本归属方法」准确） |
| `2608.20763`（VLM 路由失败诊断 MEDIUM） | **200** | **773** | "Applied to open-weight VLMs on Relay Chain -- a new cooperative grid-world benchmark we propose -- we diagnose a critical routing failure: models fail to incorporate belief representations into their next action prediction, effectively leaving valuable information about their partners unused." | ✅ 一致：《CARD: Diagnosing Belief to Action Routing Failures in Vision Language Models》 |
| `2609.04141`（测试时适配 LOW） | **200** | **1459** | "While agents are adapted towards individuals, we show these personalized agents also produce improvements in success of up to 8.8% that generalize across users." | ✅ 一致：《Efficient Test-Time Adaptation through Human-AI Interaction》（TAHI） |

**四条全部可达（HTTP 200）**，abstract 均 > 770 字符，无 404/503/timeout，无需降级。
工单 §0 的「abstract 字面验」结论在本轮得到独立复核：`2609.00267` 的标题与摘要同时出现
**Identity / Authorization / Governance** 三个关键词，确实直击 sample_target，不是靠打分靠前。

## §6 · 错误码契约（稳定）

| 码 | 触发 |
|---|---|
| `GOV_MISSING_KEY` | `HERMES_AGENT_ID_KEY` 未设置（含「启用治理但无密钥」的 fail-closed） |
| `GOV_MALFORMED` | 信封/令牌结构非法（段数、base64、缺字段、版本） |
| `GOV_BAD_SIGNATURE` | key_id 不符或 HMAC 不符 —— **伪造 agent ID 落这里** |
| `GOV_CONTENT_MISMATCH` | 内容摘要与签名不符 —— **输出被替换/注入污染落这里** |
| `GOV_TOKEN_MISSING` | 启用治理但调用未带令牌 |
| `GOV_TOKEN_EXPIRED` | 令牌已过期（场景 B） |
| `GOV_AGENT_MISMATCH` / `GOV_PROVIDER_MISMATCH` | 令牌主体与本次调用不符 |
| `GOV_AUDIT_UNWRITABLE` | 审计落盘失败 |
| `GOV_INTERNAL_ERROR` | 治理层内部异常（fail-closed） |

## §7 · 开关语义与 fail-closed 取舍

`AGENT_GOVERNANCE` 未设置 → **旁路**（`_agent_governance_block` 读完环境变量即返回，不 import 治理模块、不碰审计）；
取值 `1/on/true/yes` → 强制校验。

**fail-closed**：启用后治理层自身异常一律拒绝并返回 `{"error_type": "governance_internal_error"}`。
这与仓内 `mcpserver/scope.py` 的 fail-open **刻意相反** —— 授权判定出错时放行等于把「防冒充」变成空话；
爆炸半径由「必须显式开开关」控制。唯一例外是**审计写入失败**：审计是旁路证据层，写不进去不阻断已授权调用。

## §8 · 质量与回归（实测）

| 项 | 命令 | 结果 |
|---|---|---|
| ruff（仓库配置 `E/F/I/UP/N/SIM`，line-length 120，`--config ruffcfg/pyproject.toml`） | `ruff check mcpserver/agent_governance tests/test_agent_governance*.py` | **All checks passed!** |
| ruff 对账（`--output-format=json`，身份取 `(code, basename, message)` 排除行号） | main 版 vs 241 版 `mcpserver/mcp_manager.py` | before 1 / after 1 → **EQUAL**（未新增） |
| 新增/修改文件行尾 | 逐字节 `count(b"\r\n")` | **全 0（LF）**，含 `.sh` 与 `.py` |
| 最小差集 | `diff -u` 基线 vs 交付 | `mcp_manager.py` **+32 −0**；`peak_switch.sh` **+26 −1**（仅 usage 行改写）；台账 **+24 −5** |
| 241 新测 | `pytest tests/test_agent_governance*.py -q` | **54 passed** |
| 229 回归（改前） | 恢复 main 原版 `peak_switch.sh` 后跑 `test_peak_switch.py` | **23 passed** |
| 229 回归（改后） | 241 版 `peak_switch.sh` 跑同一套 | **23 passed**（与改前一致 → 无回归） |
| 受影响既有套件 | `mcpserver/tests/test_telemetry.py test_fault_inject.py`（两者都引用 `unified_call`） | **39 passed** |
| CLI 可跑通 | `python -m mcpserver.agent_governance selftest` | `selftest: PASS`，退出码 0 |

### 一个必须说清的事实

**`mcpserver/mcp_manager.py` 在 main 上本来就有 1 处 `I001`**（`import threading` / `from system.config import logger` 位置不合 isort 预期）。
这不是本次引入的：`ruff --check` 对 **main 原始字节**同样报 1 条，对 241 版仍报 1 条，身份（code + 文件名 + message）完全一致。
`ruff --fix` 会顺手「修好」它 —— 本单**已明确回滚该顺带改动**，保证差集只有我的 hook（`+32 −0`）。

## §9 · 未落地 / 需沈遥侧接手

| 项 | 原因 | 现成材料 |
|---|---|---|
| **真实审计落点生效** | 本机无 `~/.hermes`（工单 §4 亦要求 `.hermes/config.yaml` 仅读不写） | 设 `AGENT_AUDIT_DIR` 或直接部署到云服即可；默认值已是 `~/.hermes/audit` |
| **`AGENT_GOVERNANCE=1` 全量开启** | 需要先给各调用方发令牌（`AuthorizationAuthority.issue`），属治理上线动作 | `README.md` §接线 + `demo` 输出可作回归基线 |
| **持久密钥生成与分发** | `HERMES_AGENT_ID_KEY` 未提供 | 任一 ≥32 字节随机串即可；本单所有测试均用显式注入密钥，不依赖环境 |
| **crontab / 常驻服务** | 本单不需要（治理层是库 + 开关，无守护进程） | —— |

## §10 · 数据快照口径

* 一切「本仓存在性 / 计数 / tip」结论的基线 = **main `d13913cf7b`**，全树 25,076 条目，`truncated=false`。
* 一切「测试通过数」来自本机隔离 venv（Python 3.13.14 + pytest + ruff 0.16.8），在**真字节验证场**（`realrepo/`：从 main 按 blob 拉取的真字节 + 本次交付文件）里跑出。
* 本地开发机上的 scratchpad 工作树 **未被修改、未被提交**，仅作为 import 链可用性探针（该树 HEAD 落后 main，不可作为交付基线）。
