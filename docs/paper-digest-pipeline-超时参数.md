# 超时重试策略固化（K04）

> 生成 2026-08-30 ｜ 来源：Round2 全量 5648 篇、44 块的实测经验
> 目标：把「≤100 篇/块 + 两次调用」固化为 paper-digest-pipeline 的分块参数与子代理纪律。

## 1. 实测规律（44 块经验）

| 现象 | 结论 |
|------|------|
| 单块 >150 篇 | **超时**（LLM 长上下文 + 输出过长，逐篇一行核心写不完） |
| 单块 ≤100 篇 | **成功率 100%**（无一次超时/截断） |
| 子代理预处理（先派 subagent 逐篇过一遍再喂主 agent） | **纯浪费**：多一轮 token 往返，产出对最终 digest 无增量 |

## 2. 固化参数

- **分块上限 `CHUNK_SIZE = 100`**（硬上限；推荐 80–100）。
- **调用模式 `TWO_CALL`**：每块两次调用——
  1. 第一次调用：产出「逐篇一行核心 + Top 模式」（结构化表格）；
  2. 第二次调用：基于第一次输出产出「最有价值 3 篇 + 跨领域授粉点」。
- **子代理纪律 `NO_SUBAGENT_PREPROCESS`**：禁止在 digest 前派子代理逐篇预处理；分块后直接喂主 agent。
- **重试 `RETRY = 1`**：超时块按 100 篇上限重切一次；仍超时则降级为「仅标题 + ID」摘要行。

## 3. SKILL.md 变更摘要（供 ~/.hermes/skills/research/paper-digest-pipeline/SKILL.md 应用）

在「分块参数」章节替换/新增：

```yaml
# 分块参数（Round2 44 块实测固化）
CHUNK_SIZE: 100          # 硬上限；>150 必超时，≤100 成功率 100%
CHUNK_MODE: two_call    # 每块两次调用：先逐篇核心+Top模式，再授粉
RETRY: 1                # 超时按 100 重切一次，再超时降级标题行
```

在「子代理纪律」章节新增：

```yaml
NO_SUBAGENT_PREPROCESS: true  # 禁止 digest 前子代理逐篇预处理（token 浪费，无增量）
```

## 4. 验收对照

- [x] 总结 44 块超时规律（>150 超时 / ≤100 全成功 / 子代理预处理浪费）。
- [x] 固化参数（CHUNK_SIZE=100 / TWO_CALL / RETRY=1 / NO_SUBAGENT_PREPROCESS）。
- [x] SKILL.md 变更摘要（YAML 片段可直接粘贴，目标文件在 Linux/Hermes 侧）。
