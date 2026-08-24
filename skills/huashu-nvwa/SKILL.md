---
name: huashu-nvwa
description: 人物/专家 Skill 生成器（女娲流水线）——从调研底稿到带 FIDELITY 保真度评分的可运行 skill。用于把一手资料（访谈/字幕/文章/论文）蒸馏成人物 skill：调研抽取（extraction-framework）、skill 组装（skill-template）、质检评分（fidelity-scorecard：五维 100 分制，答题/评分 agent 分离防自评）。触发词：人物skill生成、蒸馏人物、复刻专家、skill 保真度评分、FIDELITY、nvwa、女娲、huashu。
version: 1.0.0
author: scratchpad (Agent 3, SPEC-03 Phase3)
license: MIT
source_repository: https://github.com/alchaincyf/nuwa-skill (MIT, 花叔/Huashu) — references/ 与 scripts/ 原样同步，SKILL.md 为 scratchpad 重写并接入 FIDELITY 流程
tags: [skill-factory, persona, fidelity, distillation]
enabled: true
---

# huashu-nvwa — 人物 Skill 生成流水线（含 FIDELITY 质检）

三段式流水线，全部材料在包内自包含：

```
一手资料 ──①调研抽取──> 调研底稿 ──②skill组装──> 候选skill
                                                    │
                            ③FIDELITY 质检（评分 agent ≠ 答题 agent）
                                                    ▼
                                     skill + FIDELITY 评分报告（≥80 才出厂）
```

## 流程

### ① 调研抽取 → `references/extraction-framework.md`
按框架从资料抽取：心智模型（3-7 个）、诚实边界（≥3 条）、内在张力（≥2 对）、
表达指纹（句式/用词/类比）、反模式清单、角色扮演规则（含防漂移约束）。
视频资料先跑 `scripts/download_subtitles.sh` 拿字幕，再 `scripts/srt_to_transcript.py` 转写。

### ② skill 组装 → `references/skill-template.md`
照模板把①的产物组装成 SKILL.md。多条资料用 `scripts/merge_research.py` 合并去重。

### ③ FIDELITY 质检 → `references/fidelity-scorecard.md`（本 skill 的强制出厂门）
铁律：**答题 agent 和评分 agent 必须是两个独立 agent，绝不自评自证**
（SkillLens 论文：LLM 自评准确率仅 46.4%）。

五维 100 分：立场一致性 30 ｜ 风格辨识度 20 ｜ 边缘诚实度 20 ｜ 来源透明度 15 ｜ 结构完整度 15。

产出物必须包含：
1. `SKILL.md`（候选 skill 本体）
2. `FIDELITY.md`（评分报告：五维得分、等级、失分原因、改进项）
   格式：
   ```
   # FIDELITY 评分 — <人物名> v<版本>
   | 维度 | 得分/满分 | 依据 |
   |---|---|---|
   | 立场一致性 | /30 | （3 道已知立场题逐题给分）|
   ...
   总分：__/100（A≥85 出厂 / B 70-84 修订 / C<70 返工）
   评分 agent：<与答题不同的模型/实例>；答题 agent：<...>
   ```
3. `scripts/quality_check.py` 静态检查通过（结构完整度机检）

## 验收（SPEC-03 Phase3）

- [x] references/ 与 scripts/ 与上游同步（MIT，来源见 frontmatter）
- [x] scripts 可跑：3 个 py_compile 通过 + sh 语法检查通过
- [x] FIDELITY 评分卡接入产出流程（③为强制门，评分报告为出厂必备物）

## 升级

上游更新时：重跑 `git clone https://github.com/alchaincyf/nuwa-skill`（或 zip 下载）→
覆盖 references/ 与 scripts/ → 重跑脚本语法验证 → 在本文件 source_repository 注记同步日期。
