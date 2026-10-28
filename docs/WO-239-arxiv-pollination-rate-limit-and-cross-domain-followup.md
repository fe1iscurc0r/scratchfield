# 工单 239 · 论文-限流护栏（fetch_arxiv.py 断点续跑 + sleep 20-25s）+ 4 条跨域授粉点跟单

> **⚠️ 交付状态（2026-10-17 沈遥复核）**：任务 A（改 `fetch_arxiv.py`）**结构性不可交付** —— 该文件实体在**仓库外**（`/home/ubuntu/research/papers/fetch_arxiv.py`，2026-09-28 起未改），Trae 从 GitHub 侧无法修改；任务 B/C 未见任何产物（全树无 `*授粉落地*` 目录）。证据见 `docs/workorders/reports/WO-STATUS-2026-10-17.md` §3.2。
> **处置（师傅 2026-10-17「你看着办」授权）**：任务 B/C **复活**为根 `TRAE_WORKORDER_PROMPT_AGENT_260.md`（仓内可做）；任务 A 改由**沈遥侧/师傅定夺**（仓外脚本，需显式授权才动）。

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-239 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_239.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-239-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_239.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 10-15 13:18 在 QQ 下令"把这三个 cron 产出转成工单"（授粉 / 论文 / 日报），本单负责**论文**那条
> **素材漏斗**：今天 02:15 跑批 +1363 篇入库（corpus 44551 → 45914，+4454 处理后批量入 processed_ids.txt）
> **cron 触发源**：`ad17cd9d341f` 论文流水线-每日增量扫+授粉（`0 2 * * *`），下次跑批 = 2026-10-16 02:00
> **报告原文**：`/home/ubuntu/.hermes/cron/output/ad17cd9d341f/2026-10-15_02-15-10.md`
> **累计 weekly_pollination.md**：48 段（本轮追加 2026-10-15 段）

## §0 · 沈遥已执行动作（自检 + 数据搬运）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 读 02:15 跑批产出（45 行 / 4.5 KB） | ✅ | 完整趋势 + 4 条授粉点全抓到 |
| 2 | 校验 corpus 增长曲线 | ✅ | 44551 → 45914，+1363，与 cron 报告吻合 |
| 3 | 校验 processed_ids.txt 与 corpus 对齐 | ✅ | 41460 → 45914（+4454 完全对齐）|
| 4 | 校验 weekly_pollination.md 节数 | ✅ | 48 段（从 47 段 → 48 段，本轮追加 1 段）|
| 5 | 查 10-14 跑批遗留下来的 astro-ph.IM/SR 截断问题 | ✅ | worker 自荐已写明（待跟单，**本工单任务 A 处理**）|

---

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 修 fetch_arxiv.py 限流截断（10-14 已暴露的 2 类 astro-ph.IM/SR timeout）+ 把今天跑批的 4 条跨域授粉点写进 scratchpad 工程链路 |
| **M** Measurable | ① fetch_arxiv.py 加 `--skip-cats` + `time.sleep(20~25)` 两条护栏；② 02:00 跑批**不再截断**任何类目；③ 4 条授粉点每条落 1 份 schema/SPECT/WO 子项；④ pytest 全过 |
| **A** Achievable | fetch_arxiv.py 在 `/home/ubuntu/research/papers/`，corpus 45914 已稳定 |
| **R** Relevant | 师傅三条核心技术栈（无线电/嵌入式/Agent/生物质材料）+ 邵长优惠课题 |
| **T** Time-bound | **2 天内**（任务 A 在 10-16 02:00 跑批**前**完工，任务 B/C 并行）|

---

## §2 · 任务清单

### 任务 A · 修 fetch_arxiv.py 限流护栏（**最紧迫** / 10-16 02:00 前必完工）

**症状**（10-14 跑批）：
- 31 大类轮询时，**astro-ph.IM** 与 **astro-ph.SR** 2 类超时被截断
- 轮询间隔 `time.sleep(12)` 对 arxiv API 仍偏激进

**根因分析**：
- arxiv API 单 IP 限流 ~3 req/s + burst window 较短
- 31 类 × 每类 50 篇 + 多页翻页 = 实际触发 ~150 req/min
- 当前 `sleep(12)` = 5 req/min 是安全的，但**单类内部翻页**没分页 sleep

**修法**（参考日报 SKILL 第 50-90 行"扫货流程"范式）：

```python
# fetch_arxiv.py 关键改动
import argparse, json, time, pathlib

CATS_31 = ["cs.AI", "cs.LG", "cs.CV", ..., "astro-ph.IM", "astro-ph.SR"]  # 31 类全量

def fetch_with_skip(cats_to_fetch: list[str], ...):
    """支持 --skip-cats 跳过已成功抓过的类目，断点续跑"""
    for cat in cats_to_fetch:
        try:
            results = query_arxiv(cat, max_results=50)
            corpus.extend(results)
            time.sleep(random.uniform(20, 25))   # 20-25s 抖动（防 burst 检测）
        except (Timeout, ArxivError) as e:
            failed.append((cat, str(e)))
            # 不 throw，留给下次 --skip-cats 跳过

# CLI
parser = argparse.ArgumentParser()
parser.add_argument("--skip-cats", nargs="*", default=[], help="跳过指定类目（断点续跑）")
parser.add_argument("--only-cats", nargs="*", default=[], help="只跑指定类目（重跑单类）")
parser.add_argument("--sleep-min", type=int, default=20)
parser.add_argument("--sleep-max", type=int, default=25)
```

**验收 grep/assert**：
```bash
# 1. 三个新 CLI 参数都已存在
python3 fetch_arxiv.py --help | grep -E -- "--skip-cats|--only-cats|--sleep-min" | wc -l  # = 3

# 2. 单类跑通（用 --only-cats 试 astro-ph.SR）
python3 fetch_arxiv.py --only-cats astro-ph.SR --max-results 10  # 成功落 10 篇

# 3. 断点续跑（模拟：先跑后跳过）
python3 fetch_arxiv.py --skip-cats cs.LG cs.CV  # 跳过已成功的类目

# 4. 02:00 跑批（10-16）不截断
# 期望 31 类全量完成，无 timeout
```

**风险边界**：
- ❌ 不在本任务：改 arxiv API 调用库 / 改 corpus 存储格式 / 改 processed_ids 流程
- ✅ 仅在 fetch_arxiv.py 加 3 个 CLI 参数 + sleep 抖动 + try/except 容错

### 任务 B · 4 条跨域授粉点跟单（**核心增量** / 师傅方向对接）

今天跑批的 4 条授粉点已写在 `weekly_pollination.md` 第 48 段，本任务为每条生成 1 份 schema/SPECT 落地文件：

#### B-1 · Ghostline → ESP32-S3 + SX1278 + NEO6M
- **方向**：六节点 ESP32-S3 CSI 运动追踪 → 平移 SX1278 LoRa 多节点 mesh / QRP 传播预测 / 室内定位
- **落点**：`research/授粉落地/Ghostline-ESP32-LoRa-Mesh.md`
- **目标**：
  1. 抽 Ghostline 6 节点 CSI 链路的核心数据结构（节点拓扑 + CSI 矩阵 + 时序对齐）
  2. 平移到 SX1278 LoRa（433/868/915 MHz，扩频）多节点 mesh
  3. 对接师傅现有 `IC-705 + ESP32-S3 SuperMini + SX1278 + NEO6M` 硬件栈
- **预期 SPEC 字段**：节点数 / 数据率 / 时钟同步 / 拓扑 / 链路预算

#### B-2 · Object-Bound Confinement + ARMOR → NEKO harness
- **方向**：对象按身份而非名字绑定（命名空间混淆拦截）+ schema-preserving 资源约束 → 套"读大文件/写 GitHub/开工单"高副作用操作
- **落点**：`research/授粉落地/Object-Bound-ARMOR-NEKO-Harness.md`
- **目标**：
  1. 抽 Names Are Not Objects 的身份哈希引用模式
  2. 抽 ARMOR 的 IoT/边缘 schema-preserving 资源约束门
  3. 套到 NEKO 工具的**高副作用操作白名单**：read_file >10MB / write_file 改 scratchpad / gh workflow / workorder_drafts 写入
- **预期 SPEC 字段**：身份 hash 算法 / 资源 schema / 约束门触发条件 / 拦截动作

#### B-3 · UV-cured PVA-collagen + STAMP → 木质素 NPs/共熔凝胶
- **方向**：UV 固化 PVA-collagen 光固化水凝胶 + STAMP 拓扑碎片语言补 lignin 单体-低聚物-聚集表征
- **落点**：`research/授粉落地/UV-cured-PVA-collagen-STAMP-Lignin.md`
- **目标**：
  1. UV 固化 PVA-collagen 配方 → 木质素基光固化水凝胶拼图（邵长优惠课题"光固化"方向直接对接）
  2. STAMP 显式碎片语言 → lignin 单体-低聚物-聚集多尺度表征
  3. 写一份 `lignin_uv_curable_schema.json` schema
- **预期 SPEC 字段**：UV 波长 / 引发剂 / 固化时间 / 单体/低聚物/聚集阈值 / STAMP 碎片规则
- **关联**：与 WO-238 任务 C 的 reactor_digital_twin 接入协同（反应器级数字化）

#### B-4 · Mind Your Own Role + EAIR + SEPM → NEKO 多 Agent 编排
- **方向**：任务图记忆结构 → 升级工单流水线 drafts→ready→running→done 为可回放图结构
- **落点**：`research/授粉落地/SEPM-NEKO-Agent-Task-Graph.md`
- **目标**：
  1. 抽 SEPM 任务图记忆（节点 = 任务，边 = 依赖，附 metadata）
  2. 把 scratchpad/research/workorder_drafts/ 流水线从"线性列表"升级为"图结构"
  3. 接入 NEKO 多 Agent 编排（MCP / Skill / 耦合三层的"任务依赖图"视图）
- **预期 SPEC 字段**：节点 schema / 边 schema / 状态机 / 回放机制

**验收 grep/assert**：
```bash
# 1. 4 份落地 md 全部存在
ls research/授粉落地/{Ghostline-ESP32-LoRa-Mesh,Object-Bound-ARMOR-NEKO-Harness,UV-cured-PVA-collagen-STAMP-Lignin,SEPM-NEKO-Agent-Task-Graph}.md | wc -l  # = 4

# 2. 每份 ≥ 500 字 + 含 SPEC 字段表
for f in research/授粉落地/*.md; do
  if [ $(wc -c < $f) -lt 3000 ]; then echo "TOO SHORT: $f"; fi
done
```

### 任务 C · 5 个下一轮跟踪类目（**轻量** / 进 priority queue）

跑批"下一轮跟踪"段落的 5 个类目，本任务只建跟踪索引，不施工：

| 类目 | 跟踪文件 |
|------|----------|
| eess.SP OTFS/ODDM/OTSM/OCDM 延迟域波形 | `research/跟踪/eess-SP-OTFS-ODDM.md` |
| eess.AS Oído-on-MCU 后续（int8 Conformer-CTC 落 ESP32-S3）| `research/跟踪/eess-AS-Oido-MCU.md` |
| cs.CR System One/二模型攻防配对 | `research/跟踪/cs-CR-System-One.md` |
| 论文限流（任务 A 实施后） | `research/跟踪/arxiv-rate-limit-post-fix.md` |
| 31 大类全量跑通 | `research/跟踪/arxiv-31-cats-coverage.md` |

**验收 grep/assert**：
```bash
ls research/跟踪/*.md | wc -l  # ≥ 5
```

---

## §3 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-239-arxiv-pollination-rate-limit-and-cross-domain-followup.md`（本文件）
- **fetch_arxiv.py**：`/home/ubuntu/research/papers/fetch_arxiv.py`（任务 A 改这个）
- **4 份授粉落地**：`/home/ubuntu/research/授粉落地/<4 份>.md`（任务 B）
- **5 份跟踪**：`/home/ubuntu/research/跟踪/<5 份>.md`（任务 C）
- **corpus / weekly_pollination**：保持现有路径不动

---

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| 改 fetch_arxiv.py 后**单类超时** | 加 --only-cats 单独重跑，不破坏全量 |
| 20-25s sleep 让 31 类跑批变慢 | 接受（每类 ~25s × 31 = 12.75 min），但比 401 截断强 |
| 4 份授粉落地的 SPEC 字段表过于具体 | 留 P1 / P2 段给师傅补充 |
| SEPM 任务图升级可能影响 NEKO 主流程 | 任务 B-4 标"不并入主仓，先建索引" |
| UV-cured PVA-collagen 涉及邵组课题细节 | 任务 B-3 默认"通用 lignin 光固化范式"，**不**碰邵组内部数据 |

**不在本工单范围**：
- WO-238 授粉-轮 41 弹药入仓（独立工单）
- WO-240 日报 11 个新候选评估（独立工单）
- 改 arxiv MCP 工具或换 arxiv 调用库
- 改 corpus 存储格式 / processed_ids 流程

---

## §5 · 验收不变量

```bash
# 任务 A：fetch_arxiv.py 限流护栏
python3 /home/ubuntu/research/papers/fetch_arxiv.py --help | grep -E -- "--skip-cats|--only-cats|--sleep-min" | wc -l  # = 3
# 10-16 02:00 跑批：corpus 日增量 ≥ 1300，零 timeout 截断

# 任务 B：4 份授粉落地
ls /home/ubuntu/research/授粉落地/*.md | wc -l  # ≥ 4
for f in /home/ubuntu/research/授粉落地/*.md; do wc -c < $f; done | awk '$1 < 3000 { bad++ } END { exit (bad > 0) }'  # 全过

# 任务 C：5 份跟踪
ls /home/ubuntu/research/跟踪/*.md | wc -l  # ≥ 5

# 整体守卫
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-report /tmp/wo239_final.md --detect-upstream
# 期望输出：FAIL=0
```

---

## §6 · 与已有工单 / 跑批的关系

| 现有 | 关系 |
|------|------|
| cron `ad17cd9d341f` 论文流水线-每日增量 | **改造对象**（任务 A）|
| WO-237 灵感素材库 RAG | **关联**（任务 B 的 RAG 思路复用）|
| WO-238 授粉-轮 41 弹药入仓 | **协同**（任务 B-3 lignin_uv_curable_schema 与 WO-238 reactor_digital_twin 协同）|
| weekly_pollination.md 第 48 段 | **数据源**（4 条授粉点来源）|

---

> 沈遥出单 · 师傅 1 句话确认/调整后转 Trae
