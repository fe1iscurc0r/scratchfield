# 授粉漏斗 v2 演进 Changelog

> **上游设计稿**：`research/workorder_drafts/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md`
> （2026-10-11 用户口头确认通过；本文是它的唯一演进台账）
> **建立**：工单 239 · **数据快照**：main `7c017a01ee`（2026-10-14）
> **最近更新**：v2.4 · 快照 main `17d50f26fa`（2026-10-14）· 全树 `git/trees?recursive=1` = **25,114 条目，`truncated=false`**

本文件同时是**三个日报 cron 的内容源** —— §5 提供三段机器可读锚点，
GitHub 扫货日报 / 论文流水线 / 授粉流水线 各取一节追加到报告末尾（接入方式与**未落地原因**见 §5.4）。

---

## 阅读须知 · 可验证性口径

本仓已连续五次出现「工单/设计稿声称某资产已落盘，实际主仓检索不到」
（工单 210 / 228 / 229 / 237 / **本单 239**）。因此本文对每条资产强制标注：

| 标记 | 含义 |
|---|---|
| ✅ | 本仓 main 可验证 —— 附路径 + blob sha 前 10 位 |
| ⚠️ | 声称已落盘，但**本仓全树检索 0 命中** —— 附声称路径 + 检索结果 |
| 📤 | 已合入主仓 —— 附 PR 号 + squash commit |

检索基线：main `7c017a01ee` 的 `git/trees?recursive=1` → **25,063 条目，`truncated=false`**
（非截断响应，故「0 命中」是可靠结论，不是分页假象）。

---

## v2.0 (2026-10-11) · 初版设计

### Added · 本仓可验证（5 项）

- [x] ✅ **设计稿落地** —— `research/workorder_drafts/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md`
      （8,232 B · blob `d1cc310975`）。
      ⚠️ 工单 239 §1.1 把它记作 `docs/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md`，实况在 `research/workorder_drafts/`。

- [x] ✅ **灵感素材分流 5 个落点** —— `mcpserver/material_science/synth_rag/corpus/inspiration_pool_2026-10-11/`
      合计 **3,286 条 / 5 主题 / 4,331,944 B**：

      | 主题 | 条数 | index.json | blob |
      |---|---:|---:|---|
      | biomass | 2,240 | 2,945,935 B | `0ec30ca081` |
      | sdr | 1,010 | 1,317,531 B | `311b54bdf1` |
      | agent | 33 | 43,924 B | `6041a08803` |
      | esp32 | 3 | 4,017 B | `ea6ab58e7c` |
      | other | 0 | 174 B | `d570f10b3d` |
      | **合计** | **3,286** | **4,331,944 B** | |

      ⚠️ 工单 239 §1.1 把它记作 `~/research/inspiration_pool_rag/2026-10-11/`，实况在
      `mcpserver/material_science/synth_rag/corpus/`。

- [x] ✅ **工单种 8 份** —— 全部在 `research/workorder_drafts/`：

      | 工单种 | 主题 | 位置 | blob |
      |---|---|---|---|
      | WO-230-bio-A-experimental-design-and-execution | biomass | 活跃 | `99cb9ca38e` |
      | WO-231-bio-B-kb-rag-governance-multimodal | biomass | 活跃 | `b1a280c7e7` |
      | WO-232-sdr-rf-protocol-signalproc | sdr | 活跃 | `32879a4c77` |
      | WO-233-agent-agent-governance-audit | agent | 活跃 | `ceeeb9da63` |
      | WO-237-bio-C-inspiration-pool-rag-indexing | biomass | 活跃 | `a751e1c5eb` |
      | WO-234-esp32-lora-data-stability | esp32 | `archived_2026-10-11_run_three/` | `952a8e76f3` |
      | WO-235-pcb-pcb-topology-kb | pcb | `archived_2026-10-11_run_three/` | `abd36188ce` |
      | WO-236-other-cross-line-protocol-gov | other | `archived_2026-10-11_run_three/` | `91df84d4df` |

      ⚠️ 工单 239 §1.1 与设计稿 §0 均记作「**7** 工单草稿」，实况 **8 份** ——
      WO-234/235/236 于同日落入 `archived_2026-10-11_run_three/`，未被计入"7"。

- [x] ✅ **灵感素材可检索** —— `docs/inspiration_index.md`（13,291 B · blob `ab14e3168c`）
      + 检索层 `mcpserver/material_science/synth_rag/inspiration.py`
      （`search_inspiration()` / `available_themes()`，工单 237 交付）

- [x] ✅📤 **WO-237 RAG 接入** —— PR **#327** → squash `7c017a01ee`
      （物料 PR #326 先合 `d0e6bc8951`）

### ⚠️ 声称已完成、但主仓不可验证（3 项）

| 设计稿动作 | 声称产出 | 本仓检索结果 |
|---|---|---|
| 动作 1 · 入选打分脚本 | `tools/insight_scoring_v2.py` | `insight_scoring` 全树 **0 命中** |
| 动作 2 · 工单种拆分 | `WO_harness/{light,heavy}_candidates.json` | `WO_harness` / `wo_harness` 全树 **0 命中** |
| 动作 1.5 · abstract 缓存 + v3 重打分 | `RESCORE-V2-2026-10-11.json`（设计稿写 V2） | `RESCORE` 全树 **0 命中** |

> **但动作 1.5 的产物已落本仓且可溯源**：5 个素材 `index.json` 的 `meta.source` **全部指向 RESCORE-V3** ——
> biomass / sdr 写全 `RESCORE-V3-2026-10-11.json`，agent / esp32 / other 用截断形式 `RESCORE-V3`；
> `meta.ts` 五个全为 `2026-10-11`。
> ⇒ 打分脚本与 RESCORE 原件在**沈遥侧**（设计稿 §2 明示路径 `/home/ubuntu/research/…`），
> 其产出 3,286 条已随 WO-237 落仓 —— 属「下游可见、上游不可见」，**需沈遥确认原件是否回收入仓**。
>
> ⚠️ 顺带发现**上游生成脚本的 `meta` 写法不统一**：只有 biomass 带
> `meta.method = "abstract-literal-keyword-match"`，其余 4 个主题**没有 `method` 字段**；
> `source` 也有"写全名 / 写截断名"两种。若后续要按 `meta` 做机器聚合，需先统一 schema。

### Changed · 命名偏差（设计稿 vs 实况）

| 设计稿写的 | 实况 |
|---|---|
| 动作 1 输出 `RESCORE-V2-2026-10-11.json` | 素材源自 `RESCORE-**V3**-2026-10-11.json`（V2 从未出现） |
| 动作 2 输出 `WO_harness/…` | 实为 `research/workorder_drafts/` |
| 素材落点 `~/research/inspiration_pool_rag/2026-10-11/` | `mcpserver/material_science/synth_rag/corpus/inspiration_pool_2026-10-11/` |
| 设计稿正本在 `docs/` | 正本在 `research/workorder_drafts/` |

---

## v2.1 (TBD) · 待办

- [ ] **WO-239（本单）** 接入日报 —— ⚠️ **部分未落地**，原因见 §5.4（本机无 `~/.hermes`）
- [x] ~~**WO-240** sync pad→field 三防线修复~~ —— ⚠️ **本台账此前把标题记错了**。
      2026-10-14 按 `TRAE_WORKORDER_PROMPT_AGENT_240.md` 实况更正为
      **「日报 → 工单 自动转化器（cron 闭环漏斗 2.0）」**，并已交付：
      `tools/cron_to_workorder.py`（+ `tools/test_cron_to_workorder.py`，91 用例）·
      `cron/cron_to_workorder_daily.sh` ·
      首批 5 份草稿 + `_manifest.json`（`research/workorder_drafts/auto_2026-10-14/`）·
      `reports/cron_to_workorder_launch_2026-10-14.md`。
      ⚠️ **未落地**：crontab 注册 / 微信投递（本机无 `crontab`、无 `~/.hermes`）。
      ⚠️ **工单 §2 的 5 个 cron 产出路径只有 1 个与实况一致**（详见该报告 §2 对账表）。
- [x] ~~**WO-241** abstract 真伪判定（M3 重做）~~ —— ⚠️ **又一处记错（本台账第二次）**：
      本行与下一行**共用 241 号**，而 `TRAE_WORKORDER_PROMPT_AGENT_241.md` 首行实为
      **「多 agent 身份授权 + 运行时治理（漏斗 2.0 轻量猎手第 1 单）」**。
      2026-10-14 已按该实况交付（见下一行）。**「abstract 真伪判定」作为独立待办保留**，
      编号请沈遥重新指派——勿与本次交付混算。
- [x] ~~**WO-241~243** 轻量猎手三单~~ —— **第 1、2 单已交付**，第 3 单（WO-243）待做。
      241 交付物：`mcpserver/agent_governance/`（身份 HMAC-SHA256 签名 / 短期授权令牌 / JSONL **append** 审计三件套）·
      接线 `mcpserver/mcp_manager.py::unified_call`（`+32 −0`，开关 `AGENT_GOVERNANCE` **默认关闭**）·
      `tools/agent_rekey.sh` + `tools/peak_switch.sh`（峰谷切换后重签，输出 `re-sign count`）·
      `tests/test_agent_governance*.py`（54 用例）· `reports/workorder241_agent_governance_2026-10-14.md`。
      ⚠️ **工单写的 `core/agent_governance/` 在本仓不存在**（全树 `core/` 0 命中），
      已规范化落到 `mcpserver/agent_governance/`；hook 点 `llm_gateway/dispatcher.py` 亦不存在，
      改接真正的统一派发点（详见该报告 §2 对账表）。
- [x] ~~**WO-242** Prompt→RF 工程工作流 · SDR 工具集~~ —— **已交付**：
      242 交付物：`mcpserver/rf_workflow/`（`lora_phy.py` 纯标准库**唯一真值源**：符号时长 / ToA / 能量 / 链路预算 / 频谱占用 40+ 指标 ·
      `prompt_to_script.py` 生成自包含沙箱脚本 · `sim_runner.py` 串行 / 超时 / 日志归一化 · `explainer.py` 规则 + 可选 LLM ·
      `server.py` `RfWorkflowBridge` 5 工具 · `agent-manifest.json` Format A）·
      `sandbox/rfw-20261014-lora433-sf7/`（7 件 PoC 产物）· `docs/integration-graph/rf_workflow.txt` ·
      `tests/test_rf_workflow.py`（33 用例）· `reports/workorder242_rf_workflow_2026-10-14.md`。
      PR **#332** → squash `17d50f26fa`（**19 文件全新增、0 既有文件改动**）。
      ⚠️ **工单写的 `mcpserver/sdr/` / `core/sdr_signal/` / `core/rf_brain/` / `mcpserver/kicad-mcp/`**
      **在本仓全 0 命中**，已按工单 §2 指定落点规范化到 `mcpserver/rf_workflow/`（第九次路径偏差）。
      ⚠️ 本条目由 **2026-10-14 补记**（242 合并当时漏记，见同批交付说明）。
- [ ] **WO-244** toolknit CLI（PDF / PPT / 图像 MCP 工作台）
- [ ] **abstract 错位修复**（v4 漏斗）
- [x] ~~闭环统计首期报告~~ → **WO-238 已提前交付**：
      `reports/workorder_conversion_stats_initial_2026-10-11.md`
      （PR **#328** → squash `6e6982059d`；配套脚本 `tools/workorder_conversion_stats.py`，35 用例）

---

## 月度指标（量化漏斗 2.0 §5 验收）

### 3.1 工单线 · 唯一真源 = `tools/workorder_conversion_stats.py`

数据快照 main `7c017a01ee`（2026-10-14，即 WO-238 合并前）。**WO-238 自身未计入**
（它的 squash 提交 `6e6982059d` 在快照之后）。

| 月份 | 工单发放 | 主仓合入 | 转化率 |
|---|---:|---:|---:|
| 2026-08 | 39 | 0 | 0.0% |
| 2026-09 | 84 | 8 | 9.5% |
| **2026-10** | **55** | **29** | **52.7%** |
| **合计** | **178** | **37** | **20.8%** |

`--period 30d`（近 30 天）：发放 **92** / 合入 **37** / 转化率 **40.2%**。
主题线（全期）：biomass 2/3 · sdr 0/4 · pcb 2/2 · other 33/169 · agent 与 esp32 各 0/0。

### 3.2 素材线

| 阶段 | 数量 | 口径 | 本仓可验证 |
|---|---:|---|:--:|
| 论文（GLM 单遍提） | 13,488 | 设计稿 §0 | ⚠️ |
| 目标场景条目 | 6,126 | 设计稿 §0；GLM 二提库 `EXTRACT-SUMMARY-2026-10-10.json` | ⚠️ |
| Tier1 素材 | 308 | 设计稿 §0 | ⚠️ |
| **灵感素材分流** | **3,286** | 5 个 `index.json` 实测求和 | ✅ |
| 工单种 | 8 | `research/workorder_drafts/` 实测 | ✅ |
| 根目录 TRAE 工单 | 45 | main 根实测 | ✅ |

> 设计稿 §0 画的三段漏斗（13,488 → 6,126 → 308 → 7 工单）里，**上游三段全部只存在于设计稿文字**，
> 本仓无法复核。能复核的只有末两段（3,286 素材 / 8 工单种）。

### 3.3 §5 目标对账

| §5 目标 | 当前 | 判定 |
|---|---|---|
| 月度转化率 ≥ 50% | 2026-10 = **52.7%** | ✅ 达标（**首次越线**） |
| 同上，全期 | **20.8%** | ❌ 未达标（8/9 月存量拖累） |
| 6 个月内 ≥ 30 模块合入主仓 | **37** | ✅ 达标 |

> **读数提示**：52.7% 是本月首次越 50% 线，但全期 20.8% 说明 8/9 月的存量工单基本没转化 ——
> 与设计稿 §0 的诊断（末端「产出 → 合入」有隐性损耗）一致。**别只摘月度这行好看的。**

---

## §5 · 三个日报 cron 的内容源（机器可读锚点）

工单 239 §1.2 要求三个 cron 在报告末尾各追加一小节。下面三段用 HTML 注释做锚点，
日报侧按锚点切片即可 —— **不依赖任何 JSON schema**，`sed` 就能取：

```bash
sed -n '/DAILY-CRON:1-START/,/DAILY-CRON:1-END/p' docs/POLLINATION-FUNNEL-v2-CHANGELOG.md
```

### 5.1 锚点 1 · 漏斗 2.0 本周进展 → GitHub 扫货日报 `a37ffecbd730`

<!-- DAILY-CRON:1-START -->
**漏斗 2.0 本周进展**

- v2.0 已交付：设计稿 1 · 灵感素材 3,286 条（5 主题）· 工单种 8 份 · WO-237（RAG 接入）· WO-238（闭环统计）
- v2.2 已交付：**WO-240 日报→工单自动转化器**（`tools/cron_to_workorder.py`，91 用例）——漏斗末端断头路打通
- v2.3 已交付：**WO-241 多 agent 身份-授权-审计三件套**（`mcpserver/agent_governance/`，54 用例）——轻量猎手轨首单落地
- v2.4 已交付：**WO-242 Prompt→RF 工程工作流**（`mcpserver/rf_workflow/`，33 用例，19 文件全新增）——轻量猎手轨第 2 单落地
- 转化率：本月 52.7%（首次越 50% 线）· 近 30 天 40.2% · 全期 20.8%
- v2.1 待办 4 项（WO-239 日报接入 / 轻量猎手第 3 单 WO-243 / WO-244 / v4 漏斗），
  另有交接：WO-240（crontab、微信）+ WO-241（真实审计落点、`AGENT_GOVERNANCE` 上线）
- 台账：`docs/POLLINATION-FUNNEL-v2-CHANGELOG.md`
<!-- DAILY-CRON:1-END -->

### 5.2 锚点 2 · 灵感素材增量 → 论文流水线-每日增量 `ad17cd9d341f`

<!-- DAILY-CRON:2-START -->
**灵感素材增量**

| 主题 | 条数 | index.json 体积 |
|---|---:|---:|
| biomass | 2,240 | 2,945,935 B |
| sdr | 1,010 | 1,317,531 B |
| agent | 33 | 43,924 B |
| esp32 | 3 | 4,017 B |
| other | 0 | 174 B |
| **合计** | **3,286** | **4,331,944 B** |

快照 2026-10-11；口径与检索入口见 `docs/inspiration_index.md`。
<!-- DAILY-CRON:2-END -->

### 5.3 锚点 3 · 工单种生成进度 → 授粉流水线-超限战轮 `bda7241fa9c3`

<!-- DAILY-CRON:3-START -->
**工单种生成进度**

- 活跃工单种 5：WO-230 / 231 / 232 / 233 / 237（`research/workorder_drafts/`）
- 已归档工单种 3：WO-234 / 235 / 236（`research/workorder_drafts/archived_2026-10-11_run_three/`）
- 已转正式工单 45 份：main 根 `TRAE_WORKORDER_PROMPT_AGENT_*.md`
- 待办 4 项（见 §v2.1；WO-240、WO-241、WO-242 已于 2026-10-14 交付）
<!-- DAILY-CRON:3-END -->

### 5.4 接入状态 · ⛔ 未落地（本机环境不具备，实测）

| cron id | 名称 | 要追加 | 状态 |
|---|---|---|---|
| `a37ffecbd730` | GitHub 扫货日报 | 5.1 漏斗 2.0 本周进展 | ⛔ **未接入** |
| `ad17cd9d341f` | 论文流水线-每日增量 | 5.2 灵感素材增量 | ⛔ **未接入** |
| `bda7241fa9c3` | 授粉流水线-超限战轮 | 5.3 工单种生成进度 | ⛔ **未接入** |

**为什么未接入**（2026-10-14 本机实测）：

| 检查 | 命令 | 结果 |
|---|---|---|
| hermes 配置目录 | `ls -d ~/.hermes` | `No such file or directory` |
| hermes CLI | `which hermes` | `not found` |
| 系统 cron | `which crontab` | `not found` |

⇒ 工单 239 §2 任务二要的 `hermes cron edit` 在本机**无法执行**；三个 cron 的现有 `prompt_preview`
也不在本仓（cron 池在沈遥侧）⇒ **连"改前 / 改后 diff"都给不出**。

**交接给沈遥的改法**（三处各追加一段，不动 schedule / deliver）：

> 在 `prompt_preview` 末尾追加：「读取 `docs/POLLINATION-FUNNEL-v2-CHANGELOG.md` 中
> `DAILY-CRON:n-START` 到 `DAILY-CRON:n-END` 的区块，原样追加到报告末尾的
> 〈第 N 节标题〉小节；区块缺失时静默跳过，不要报错。」

具体 CLI 参数请以沈遥侧 `hermes cron edit --help` 为准 ——
**本机无 hermes，语法不做猜测**（猜出来的命令只会让人白跑一趟）。

---

## §6 · 相关文件

| 文件 | 作用 |
|---|---|
| `research/workorder_drafts/POLLINATION-FUNNEL-v2-DESIGN-2026-10-11.md` | 上游设计稿（正本） |
| `docs/inspiration_index.md` | 灵感素材索引入口（3,286 条口径 + 检索样例） |
| `mcpserver/material_science/synth_rag/inspiration.py` | 素材检索层 |
| `tools/workorder_conversion_stats.py` | 工单线指标唯一真源（§3.1 的四张表由它产出） |
| `tools/cron_to_workorder.py` | **日报 → 工单草稿自动转化器**（WO-240） |
| `cron/cron_to_workorder_daily.sh` | 日报→工单 日更脚本（06:00，⛔ crontab 未注册） |
| `reports/cron_to_workorder_launch_2026-10-14.md` | WO-240 交付报告（含 cron 路径对账表） |
| `mcpserver/agent_governance/identity.py` | 输出签名 / 验签（HMAC-SHA256，WO-241） |
| `mcpserver/agent_governance/authorization.py` | 短期授权令牌（默认 1h，WO-241） |
| `mcpserver/agent_governance/audit.py` | 运行时审计（JSONL **append**，禁 `json.dump`，WO-241） |
| `mcpserver/mcp_manager.py` | 统一派发点：agent_governance guard hook（WO-241，**默认旁路**） |
| `tools/agent_rekey.sh` | 峰谷切换后重签挂起任务，输出 `re-sign count`（WO-241） |
| `reports/workorder241_agent_governance_2026-10-14.md` | WO-241 交付报告（含路径对账表 + arXiv 链接复查表） |
| `mcpserver/rf_workflow/lora_phy.py` | LoRa chirp 功率估算**唯一真值源**（纯标准库，WO-242） |
| `mcpserver/rf_workflow/sandbox/` | 自包含沙箱 PoC 产物（WO-242） |
| `reports/workorder242_rf_workflow_2026-10-14.md` | WO-242 交付报告（含路径对账表 + arXiv 链接复查表） |
| `reports/workorder_conversion_stats_initial_2026-10-11.md` | 闭环统计首期基线 |
| `reports/pollination_funnel_v2_launch_2026-10-11.md` | 漏斗 2.0 启动报告（工单 239 任务三） |
| `docs/2026-09-07-授粉日报论文-总台账.md` | 授粉日报/论文线的既有总台账（另一条线，未合并口径） |
