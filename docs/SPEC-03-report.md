# SPEC-03 验收报告：NEKO 记忆层工程化 + 授粉落地

日期：2026-08-22 ｜ 执行：Agent 3（scratchpad 内嵌 agent）｜ 测试：17/17 passed（1.26s）

## 侦察修正（SPEC 与现实的差异，先说清）

1. **"NEKO 缺混合检索"已过时**：`memory/hybrid_recall.py` 已有 BM25+cosine 双路 RRF（k=60）。Phase1.1 因此改为**旁路第二实现 + 对照评测**（可独立测试、可做 A/B），不重复造轮子也不动现有实现。
2. **mem0 对照报告不存在**（`docs/记忆层-对照评估.md` 未产出），仓内无可复现的 mem0 基线。验收对照基线改为：**关键词单路（FTS5-only） vs RRF 混合路**，参考线 = MemClaw LoCoMo 77.6%（LLM-judge 口径，vendor/top5/caura-memclaw/BENCHMARKS.md）。
3. **huashu-nvwa 原不存在**，全新创建；**nuwa 上游** git clone 因网络失败，改 zip 通道成功（32MB）。
4. bge-small-zh 在 `rag/` 模块（torch），NEKO 自身用匿名 ONNX profile——旁路模块不依赖任何一方，向量接口中立（list[float]）。

## Phase 1 记忆层升级 ✅

全部旁路实现，`git status` 断言零修改 NEKO 既有文件（测试 test_bypass_no_import_of_legacy_paths 源码级防回归）：

| 任务 | 落点 | 验收 |
|---|---|---|
| 1.1 混合检索 RRF | `NEKO/N.E.K.O/memory/hybrid_search/rrf.py` | 20 条同义改写查询 recall@2：**hybrid 0.95+ vs keyword ~0.5**（测试断言 hybrid ≥ keyword 且 ≥0.9）；RRF k=60 与仓内两套既有实现对齐 |
| 1.2 AAAK 索引卡 | `memory/index_cards/store.py` | SQLite index_cards 表：建卡/按会话查/关键词检索/touch 续命；启发式摘要（可注入 LLM summarizer）；置信度=覆盖率×信息量 |
| 1.3 会话血统 | `NEKO/N.E.K.O/memory/lineage/model.py` | 父ID+分支标记；trace 上溯到根 ✅；三重防护（父不存在/环/父上下文>40k 字符拒 fork——对齐 openclaw parentForkMaxTokens 思想，机制 MIT 同源） |
| 1.4 后台静默写入 | `memory/lifecycle/policy.py` BackgroundWriter | 提交 5 会话耗时 <50ms（非阻塞断言）；worker 线程 drain 后 5/5 写入零错误；与 chat token 零交集 |
| 1.5 记忆过期 | `lifecycle/policy.py` decay/expire | 指数衰减（14 天半衰期校准断言 0.49<w≤0.51）；keep/decay/expire 三态决策含置信度门控 |

## Phase 2 compaction 升级 ✅

`NEKO/N.E.K.O/memory/compaction_v2/branch_summary.py`（不动现有 `recent.py`）：
- **branch-summarization**：按血统分支逐支摘要再合并（root/射频/电源三分支 demo 树通过）
- **confidence 门控**：branch_confidence 综合各支覆盖率；≥0.55 才允许自动压缩，低置信保原文（防不可逆失真）
- **验收 2 实测**：4 段×3 工程对话压缩后 **token 节省 69.2%**（≥30% ✅），**信息完整率 100%**（16 关键词全命中，≥95% ✅）

## Phase 3 nuwa 同步 + FIDELITY ✅

- `skills/huashu-nvwa/` 新建：`references/`（extraction-framework / fidelity-scorecard / skill-template）+ `scripts/`（download_subtitles.sh / merge_research.py / quality_check.py / srt_to_transcript.py）**逐文件与上游字节一致**（测试断言），LICENSE-NUWA-MIT 保留，frontmatter source_repository 注明来源
- **FIDELITY 接入产出流程**：SKILL.md 三段流水线把评分卡设为强制出厂门——FIDELITY.md 为必备交付物、双 agent 铁律（答题≠评分）、五维 100 分（立场 30/风格 20/边缘诚实 20/来源 15/结构 15）、≥80 出厂
- scripts 可跑：3 个 py_compile + bash -n 全过（测试断言）

## Phase 4 流程层三件套 ✅

`skills/brainstorming`（复述+意图三问→≤2 方案→等批准）、`skills/writing-plans`（工单三件套：输入/落点/验收，格式对齐本仓工单体系）、`skills/verification-before-completion`（五关验收门）。均带本土 frontmatter（name/version/author/license/tags/enabled），独立可加载（测试断言字段齐全+内容厚度）。

**完整流程 demo 一次通过**（test_full_process_demo_once_through）：以真实需求"read_schematic.py 加 --json"走完 brainstorm→工单→验收五关三段，机器可验证形态。

## 验收对照（工单四条）

1. ✅ 混合检索 20 查询：hybrid ≥ 关键词基线（0.95 vs 0.5）；mem0 无可复现基线（见侦察修正 2），MemClaw 77.6% 参考线
2. ✅ 压缩 token 节省 69.2%（≥30%），信息完整率 100%（≥95%）
3. ✅ huashu-nvwa 含 FIDELITY 强制门 + 评分报告格式；scripts 全部可跑
4. ✅ 三件套注册可加载；完整流程 demo 自动化通过

## 硬约束核验

- **非侵入**：新增 5 个目录 + 2 个测试文件 + 报告，`git status` 零修改 NEKO 既有路径（测试含源码级 import 黑名单防回归）
- **license**：旁路模块 Apache-2.0；lineage 注明 openclaw/MIT 机制同源；nuwa 材料保留上游 MIT + 来源声明
- **skills 独立**：三件套+huashu-nvwa 无任何主流程 import

## 遗留问题

1. 评测数据集是构造的（同义改写对），接真实 48912 关记忆库跑 A/B 需要 NEKO 运行时环境（云端），建议下个工单把 hybrid_search 挂到真实数据出对照数字
2. 启发式摘要器离线可用但质量有限，LLM summarizer 注入点已留（IndexCardStore.build_card / branch_summary）
3. 后台写入目前写 index_cards 侧车表，与 FactStore 的打通（同库不同表 or 定期合并）待 NEKO 侧决策
4. EasyEDA 生命周期 fulltest 仍在等编辑器重启（另一条线，与本 SPEC 无关）
