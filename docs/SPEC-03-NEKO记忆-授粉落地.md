# SPEC-03: NEKO 记忆层工程化 + 授粉行动项落地（③④ 合并）

> 版本 v1 | 2026-08-22 | 委托：外部 agent（类 Trae）
> 定位：AI 伴侣体验质变 + 12 篇授粉报告落地

## 背景

记忆层三篇评估报告已出（mempalace/mem0/openclaw/ECC），代码未动。
授粉报告 12 篇（Batch-1/2/3 + graphify 落地 + nuwa 同源）。
本 SPEC 把"报告里的建议"变成代码。

## 目标

1. NEKO 记忆层：混合检索 + 压缩索引卡 + 会话血统 + 后台写入
2. 授粉行动项：openclaw 机制 / compaction 升级 / nuwa 同步 / 流程层 skills

## 阶段拆解

### Phase 1: 记忆层升级（核心）
- 任务 1.1: 混合检索融合（FTS5 + bge-small-zh 双路 RRF 融合，~100 行）
- 任务 1.2: AAAK 压缩索引卡（SQLite index_cards 表，会话主题→压缩卡片→定位 chunk）
- 任务 1.3: 会话血统（session-lineage：父会话 ID + 分支标记，抄 openclaw，~200 行）
- 任务 1.4: 后台静默写入（会话摘要→记忆库，subagent 处理不进 chat token）
- 任务 1.5: 记忆更新/过期（last_access + 置信度，低频降权）
- 验收: 混合检索 20 次随机查询召回率 ≥ mem0 对照；血统链可追溯

### Phase 2: compaction 升级
- 任务 2.1: branch-summarization（压缩前先做分支摘要层，抄 openclaw）
- 任务 2.2: confidence 字段（高置信才自动压缩）
- 验收: 上下文压缩 token 节省 ≥30%，信息完整率 ≥95%

### Phase 3: nuwa 上游同步
- 任务 3.1: 同步 references/（extraction-framework / fidelity-scorecard / skill-template）
- 任务 3.2: 同步 scripts/（download_subtitles / merge_research / quality_check / srt_to_transcript）
- 任务 3.3: FIDELITY 保真度评分接入 huashu-nvwa 产出流程
- 验收: huashu-nvwa 生成 skill 含 FIDELITY 评分；scripts 可跑

### Phase 4: 流程层 skills 三件套
- 任务 4.1: brainstorming（需求收敛：先问意图→出设计→等批准）
- 任务 4.2: writing-plans（SPEC → 分块任务，对齐工单格式）
- 任务 4.3: verification-before-completion（验收门）
- 验收: 三 skill 注册后可加载，能跑一次完整流程 demo

## 硬约束

- NEKO 记忆升级不破坏现有写入路径（非侵入旁路，验收断言 git diff 不触旧路径）
- 授粉代码带 license 声明（MIT/Apache 来源注明）
- skills 三件套独立可加载，不改主流程

## 远期规划（Phase 5+）

- 5.1: 记忆可视化（记忆宫殿 UI）
- 5.2: 跨实例记忆同步（yjs CRDT，WO-04 已交基础）
- 5.3: 记忆合并去重（mem0 式实体抽取）
- 5.4: 情感记忆权重（用户偏好/情绪标记）
- 5.5: 记忆导出/导入（备份恢复）

## 目录结构（预期）

```
NEKO/
├── memory/
│   ├── hybrid_search/    # 混合检索 RRF
│   ├── index_cards/      # AAAK 压缩索引卡
│   ├── lineage/          # 会话血统
│   └── lifecycle/        # 更新/过期
scratchpad/skills/
├── brainstorming/        # 流程层
├── writing-plans/
└── verification-before-completion/
huashu-nvwa/
├── references/           # 上游同步
└── scripts/
```
