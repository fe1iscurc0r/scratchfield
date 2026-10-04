# scientific-agent-skills 材料科研 Skill 弹药吸收（W102-01）

> 2026-09-09 · 落地 + 评估 · 上游：K-Dense-AI/scientific-agent-skills（43,936★，MIT，Python，163 个 Agent Skills，2026-09-07 活跃，arXiv 2609.00065）
> 许可：MIT（授粉报告已复核）
> 源码：shallow 部分克隆（--filter=blob:none --sparse set docs）到本机
> D:/my git/haul-backfill/scientific-agent-skills——以下引用为实读行号。

## 一、技能清单摸底（实读 docs/skills.md 目录，240 行 / 162 项）

生物质能源与材料直接相关（实读条目 + 行号）：

| 技能名（上游） | 功能 | skills.md 行 | 与本地重复性 |
|---------------|------|-------------|-------------|
| Database Lookup | 78 个科学/材料数据库确定性查询 | :5 | ⭕ 新（材料数据库查询可吸收） |
| Hugging Science | HF 17 域目录（含 materials-science/energy） | :13 | ⭕ 新（参考级） |
| DeepChem | 分子 ML（GNN/MoleculeNet） | :77 | ✅ 本地 deepchem skill 已有 |
| DiffDock | 扩散分子对接 | :78 | ⭕ 新（对接线） |
| Rowan | 云量子化学（DFT/xTB） | :83 | ⭕ 新（参考级） |
| BioPython | 计算生物学 | :47 | ✅ 本地 biopython 已有 |
| BioServices | 40+ 生物服务统一 API | :48 | ✅ 本地 bioservices 已有 |
| Nextflow | 可复现工作流 | :33 | ⭕ 新（参考级） |
| PrimeKG / NCATS ARAX | 生物 KG | :8/:9 | ⭕ 新（KG 线参考） |

（原草稿「材料表征/拉曼/化学式」等技能名在上游目录里并无直接对应条目——已按实读更正，
本地四件套/chemformula 复用结论不变，它们来自本地既有能力而非上游技能。）

## 二、授粉三大件①：源→目标映射

| 源组件 | 目标模块 | 授粉方式 | 收益 |
|--------|---------|---------|------|
| Database Lookup（78 数据库检索契约） | 本地 skills/ + mcpserver academic | 直接吸收候选 | 材料数据库确定性查询 |
| Skill 写法（目录 + docs/skills.md 索引） | 本地 SKILL.md 规范 | 规范对齐 | 技能可读可用 |
| DeepChem/DiffDock 等分子技能 | 本地 deepchem skill | 对照（不重复吸收） | 去重明确 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **技能目录索引**（docs/skills.md 逐项「名称+一句话能力+使用边界」，共 162 项）：
   本地 skills/ 缺统一索引页——吸收点=补 skills 索引文档。
2. **能力边界写法**（每条含「Use cases / not for」显式边界，如 :9 ARAX 的 not for 列表）：
   SKILL.md 的触发条件与边界声明同构。
3. **标准库优先**（多数技能标「Python 3.11+ standard-library scripts, no API key」，如 :12）：
   零依赖技能写法与本地纪律一致。

## 四、落地产出（本批）

本地化 3 个技能（frontmatter + 触发条件 + 步骤 + 验证，均绑本地既有能力，零新依赖）：
1. `skills/sci-biomass-characterization/SKILL.md`（TGA/DSC/XRD/Raman 四件套工作流）
2. `skills/sci-chemformula-mass/SKILL.md`（化学式/分子量，绑 chemformula_interface）
3. `skills/sci-material-literature-search/SKILL.md`（材料文献检索→卡片化，绑 PapersView）

去重对照：与本地 lumo-hamlog-log / market-research-reports 等零重叠；表征类与 data_tools 直接复用。

## 五、许可裁定与结论

MIT 可吸收；结论：**吸收（已落地 3 技能）** + 其余 7 项登记为「待后续批次（含新计算库的暂缓）」。

---
*授粉：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill）*
