# 工单 245 · docs/runbooks/ 共享索引与入口页（让 4 份 runbook 可被人类/agent 单一路径找到）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-245 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_245.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-245-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_245.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 13:50 在 QQ 下令"法律功能不用动，可以再多出一点"，本单配套 WO-244 节奏表 + WO-238/239/240/242/243 形成"产出→台账→讯报→索引"闭环
> **素材来源**：
> - `scratchpad/docs/runbooks/` 目录目前**只 WO-244 一份**节奏表
> - 但 scratchpad/docs 下散落多份 runbook/sop/runbook 性质文档（按 grep `docs/`）
> - 缺一份"docs/runbooks/INDEX.md"作为入口页
> **关联工单**：WO-244（节奏表）、WO-243（工单台账）、WO-238/239/240（产出）
> **关联工程**：WO-237 RAG 索引（接口契约参照）、README.md 主入口（被 runbook/INDEX 反向引用）

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 盘点 `scratchpad/docs/runbooks/` 目录 | ✅ | 仅 `DECISION-LAYER-SIGNAL-RHYTHM.md`（WO-244 任务 A 已规划但**未落**） |
| 2 | grep docs/ 下 "runbook" / "sop" / "应急" "On-call" / "故障处置" 字眼 | ⚠️ 间接 | 见 §A 拟入索引清单 |
| 3 | 看 README.md 是否已有 runbooks 章节 | ❌ 缺 | 主入口没有跨引到 runbooks 索引 |
| 4 | 是否 RAG 可达 | ❌ | 没有 corpus 摘要，agent 找不到 |

**核心痛点**：4 份 WO 都在向 docs/ 写文件，但散落 → 师傅昨天起就在问"我那个 docs/ 谁能找到？"，没一份索引页。

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 立 `scratchpad/docs/runbooks/INDEX.md`，把目前 docs/ 下散落的 runbook/sop/on-call 文档+本批 6 份 WO 收容到统一入口 |
| **M** Measurable | ① INDEX.md ≥ 1 张主表覆盖 8+ 份 runbook 类文档；② README.md 加一个 5 行 runbooks 章节 + 反向链接；③ 跑一次 agent 检索演示（关键词"cron 异常"命中 INDEX）|
| **A** Achievable | 纯文档 + 1 次 RAG 索引复测 |
| **R** Relevant | 师傅铁律"先查 cron，再做事" + 9 月那批 runbook 风格延续 |
| **T** Time-bound | 当天（W1 与 WO-238/239/240/242/243/244 同期 review）|

## §2 · 任务清单

### 任务 A · 立 INDEX.md（主入口）

新文件 `scratchpad/docs/runbooks/INDEX.md`：

```markdown
# docs/runbooks/ · 运维/SOP/索引入口

> 本目录是「**单点查找所有 runbook/SOP/On-call 文档**」的入口。
> 文档定位为「人类跑一次 + agent 检索一次」双受众。

## §1 · 主索引表（按主题分桶）

| 桶 | 文档 | 关键词 | 上次更新 | 关联 WO |
|----|------|--------|----------|---------|
| **决策层讯报** | DECISION-LAYER-SIGNAL-RHYTHM.md | cron 节奏 / 紧急推送 / 讯报分层 | 2026-10-15 | **WO-244** |
| **防幻觉守卫** | *(跨 runbooks，本目录)* + scripts/anti_hallucination_guard.py | 幻觉 / 反幻觉 / 验真 | 2026-08-23 起 | WO-242 |
| **工单台账** | *(跨 runbooks，本目录)* + INDEX-active.md | 工单 / WO 进度 / 状态分桶 | 2026-10-15 | WO-243 |
| **授粉流水线** | *(父目录 docs/超限战轮41-...md)* | 授粉 / 轮 41 / 反应器 / 弹药 | 2026-10-14 | WO-238 |
| **论文流水线** | fetch_arxiv.py + weekly_pollination.md | arXiv / 31 大类 / 增量 | 2026-10-15 跑批 | WO-239 |
| **GitHub 扫货** | SWEEP-*.md + github-sweep-and-classify SKILL | 扫货 / AGPL / 授粉勘察 | 2026-10-15 日报 | WO-240 |
| **数据备份** | backup_runner.sh cron (`3869dd1e933a`) + Backfill json | Gitee 星数 / 凌晨错峰 | 每日 03:00 | (cron 387 ID) |

## §2 · 索引排序与 RAG

- **RAG 语料**：INDEX.md 自身进 synth_rag corpus（按 WO-237 接口契约）
- **agent 检索权重**：本表第 1 列 "桶" 是主标签，跟 RAG schema.items[].tags 对齐
- **docs/runbooks/INDEX.md → mcpserver/material_science/runbook_corpus/index.json**：1 个新 corpus

## §3 · 不在本目录范围

- 详细 cron 实现细节 → `~/.hermes/cron/output/<job_id>/`
- 单个工单 → `scratchpad/docs/WO-*.md`
- 历史扫货归档 → `github_haul/FUSION-LOG-*.md`

## §4 · out of scope

- 不动 README.md（仅追加一行反向链）
- 不动 17 个 cron 命名（铁律）
- 不动 WO 编号

> 沈遥维护 · 13:50 · changelog 在 POLLINATION-FUNNEL-v2-CHANGELOG.md
```

**验收 grep/assert**：
```bash
# 1. INDEX.md 存在
ls scratchpad/docs/runbooks/INDEX.md
# 2. 含主表（≥ 8 行 '| '）
grep -c '^| ' scratchpad/docs/runbooks/INDEX.md  # ≥ 8
```

### 任务 B · 给 README.md 加反向链

（**最小动作**：仅追加 1 行）

```bash
# 在 README.md "## 文档" 或最末节追加（**别动**其它结构）
echo -e "\n## 运维与决策层\n\n查 cron 节奏、讯报分层、紧急推送处置 → [docs/runbooks/INDEX.md](docs/runbooks/INDEX.md)\n" >> README.md
```

**验收 grep/assert**：
```bash
# README.md 含一行反向链
grep -c "docs/runbooks/INDEX.md" README.md  # ≥ 1
```

### 任务 C · RAG 索引复测（接 WO-237 接口）

新文件 `mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json`：

```json
{
  "meta": {
    "source": "WO-245-2026-10-15",
    "method": "schema-extract",
    "ts": "2026-10-15",
    "theme": "runbook",
    "count": 1,
    "note": "docs/runbooks/INDEX.md 主入口 RAG 切片"
  },
  "items": [
    {
      "id": "docs/runbooks/INDEX.md:§1",
      "category": "doc",
      "abstract": "按主题分桶的 runbook 主索引表：决策层讯报/防幻觉/工单台账/授粉/论文/扫货/数据备份",
      "target": "查 cron 异常/讯报/守卫/工单进度/授粉落点的统一入口",
      "score": 92.0
    },
    {
      "id": "docs/runbooks/DECISION-LAYER-SIGNAL-RHYTHM.md:§A",
      "category": "doc",
      "abstract": "17 个 cron 按 🔴🟡🟢🟦 四档分类的讯报节奏表",
      "target": "判断任意 cron 属于哪一档决策层",
      "score": 88.0
    }
  ]
}
```

**验收 grep/assert**：
```bash
# 1. corpus 落盘
ls mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json
# 2. corpus meta count = 1（一个 corpus 入口） + items ≥ 2
jq '.meta.count' mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json  # = 1
jq '.items | length' mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json  # = 2
```

### 任务 D · POLLINATION-FUNNEL-v2-CHANGELOG 追加段

（接 WO-243 任务 D 模式）

```bash
cat >> scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md <<EOF

## 2026-10-15 13:50 runbooks/ 索引层
- WO-245 立 docs/runbooks/INDEX.md 主入口
- README.md 加反向链一行（最小动作）
- RAG corpus runbook_corpus 建立
EOF
```

## §3 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-245-runbooks-index.md`（本文件）
- **新增**：
  - `scratchpad/docs/runbooks/INDEX.md`
  - `mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json`
- **追加**：`scratchpad/README.md`（追加反向链 1 行）+ `scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md`（追加段）

## §4 · 风险与边界

| 风险 | 缓解 |
|------|------|
| INDEX.md 内容漂移（用了 stale 文档名）| 任务 C 跑一次 corpus 复测，命中才算 |
| README.md 改动破坏其它结构 | 任务 B **严格仅追加**，不改 |
| 本工单与 WO-244 都有 runbooks 主题 | 本工单**不**重复 WO-244 内容，只做"路径索引" |
| 法学工单（L 系列）按规则不入 runbooks/ | 任务 A 桶表**显式不列** LAW |

**不在本工单范围**：
- 改任何其他 runbook 文档的内容
- 改 cron 命名
- 改 RAG 接入机制

## §5 · 验收不变量

```bash
# 1. INDEX.md 存在
ls scratchpad/docs/runbooks/INDEX.md
# 2. README.md 反向链
grep -c 'docs/runbooks/INDEX.md' README.md  # ≥ 1
# 3. corpus 落盘
ls mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json
jq '.items | length' mcpserver/material_science/synth_rag/corpus/runbook_corpus/index.json  # ≥ 2
# 4. CHANGELOG 追加
grep -c 'runbooks/ 索引层' scratchpad/docs/POLLINATION-FUNNEL-v2-CHANGELOG.md  # ≥ 1
# 5. 不动主流程
git diff --stat -- NEKO apiserver | wc -l   # = 0
```

## §6 · 与已有工程关系

| 现有 | 关系 |
|------|------|
| WO-244 DECISION-LAYER-SIGNAL-RHYTHM.md | **入索引表** |
| WO-238/239/240/242/243 | **入索引表对应桶** |
| WO-237 RAG 接口契约 | **复用 schema** |
| `mcpserver/material_science/synth_rag/corpus/` | **新增 runbook_corpus/** |
| README.md | **追加反向链** |

---

> 沈遥出单 · 师傅 13:50 下令"再多出一点"已落 · 与本批 6 份同期 review
