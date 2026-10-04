# EXEC-REPORT-102 · 第三十七期卷102（材料科研授粉批）执行清单

**分支**：trae/agent-102 · **执行**：fe1iscurc0r · **日期**：2026-09-09

## 完成

- [x] W102-01 scientific-agent-skills 吸收（落地）
  - 技能清单 ≥10 项带分类（4 项本地已有→复用、6 项新登记）
  - 本地化 3 个技能：sci-biomass-characterization（四件套工作流）/ sci-chemformula-mass
    （绑 chemformula_interface）/ sci-material-literature-search（绑 PapersView），
    frontmatter + 触发条件 + 步骤 + 验证齐全，零新依赖
  - 报告 docs/scientific-agent-skills-授粉-2026-09-09.md（三大件 + 去重对照）
- [x] W102-02 mattergen 评估 → docs/mattergen-授粉-2026-09-09.md（暂缓/仅参考，收 schema）
- [x] W102-03 nequip 评估 → docs/nequip-授粉-2026-09-09.md（选型首选 nequip，ASE 对接锚点）

每项均含授粉三大件 + 许可裁定。

## 阻塞 / 遗留

- [ ] github_haul 候选源码快照在编排方本机（gitignore 不入库），本机不可得——
      源码行号级引用统一标注待快照回填（快照同步后行号回填补丁）。
- [ ] mattergen 权重体积、nequip 推理依赖（torch 版本/GPU）两项数据待核（标在报告内）。
- [ ] 其余 6 项新技能（热解模拟/结晶度/聚合物性质/MD 前处理/DoE 等）登记待后续批次。

## 合并

- [ ] 待用户收口：trae/agent-102 → main
