# SPEC-02 验收报告：Lumo 科研助手规模化

> 2026-08-23 | 分支 `spec02-lumo-workbench`（commit `10291308`，41 文件）
> 全量回归 **358 passed**（唯一失败为 SPEC-03 存量环境问题 `test_nuwa_scripts_runnable`，与本单无关）

## 一、16 项融合清单（Phase 1）

| # | 项目 | 许可 | 状态 | 可调用 |
|---|------|------|------|--------|
| 1 | thermo (ChEDL) | MIT | ✅ 已接入 | `academic_call thermo property name=toluene`（Tb 实测 383.75K） |
| 2 | CoolProp | MIT | ✅ 已接入 | `academic_call CoolProp property`（水密度实测 997.0） |
| 3 | ChemFormula | MIT | ✅ 已接入 | `academic_call ChemFormula parse/reaction_mass` |
| 4 | AffineGaps | Apache-2.0 | ✅ 已接入 | `academic_call AffineGaps align/score`（胰岛素比对实测） |
| 5 | Pynite | MIT | ✅ 已接入 | `academic_call Pynite cantilever`（3.0 新 API，挠度与理论解误差 7e-13） |
| 6-16 | tespy / pycalphad / Clapeyron.jl / PyXtal / SLICES / gemmi / hyalite / WaveBench / rp2daq / hololinked / FEMcy | 见 LICENSES.md | 📖 MODEL_INTERFACE.md 就绪 | 按需安装后扩 CALLERS |

- 每项均有 `academic/<项目>/MODEL_INTERFACE.md`（算法/API/数据格式/Lumo 用途/引用）
- 索引：`academic/README.md`；许可声明：`academic/LICENSES.md`
- ⚠️ 许可风险：gemmi 实为 MPLv2/LGPLv3（非白名单口径），已标注且默认不自动调用；SLICES/FEMcy 标 `*` 待复核
- 工具：`academic_status`（16 项清单 + 可调用计数）、`academic_call`（5 项实调，护栏齐全）
- 验收：10/10 测试绿，`callable_installed ≥ 5` ✅

## 二、GraphRAG 实测（Phase 2）

模块 `mcpserver/material_science/graphrag/`（store / importer / vector_index / query / tools）：

- **图谱导入**：`vault/**/*.md`（12 篇材料笔记）+ `academic/*/MODEL_INTERFACE.md`（16 篇）→ doc/section 节点 + contains 边 + 词元共现 mentions 边 + 连通分量社区；全量重建幂等，落盘 `%APPDATA%/Lumo/graphrag/graph.json`
- **向量**：复用 `rag.embedding_engine`（bge-small-zh-v1.5 单例，不另起模型），`vectors.npz` + `node_ids.json`；模型不可用时如实降级词元打分（不伪装随机向量）
- **查询实测**："木质素基碳材料的制备方法" → 返回图谱路径（所属文档 → 命中节）、原文摘录、相邻节（mentions）、社区文档清单，**耗时 <5s**（6/6 测试绿，含真实语料+真实嵌入用例）
- 工具：`graphrag_import` / `graphrag_query` / `graphrag_stats`
- 零触碰 SQLite RAG 主链路（只读旁路，独立数据目录）✅

## 三、duckdb 工作台 demo（Phase 3）

模块 `mcpserver/material_science/duckdb_workbench/`：

- `import_template.csv` 导入模板（11 列实验口径）+ `duckdb_import`（CSV/Excel，fail-fast 空文件）
- 三标准分析：描述统计 / 分组对比（自动推断分组列：排除常数列与每行唯一列，取基数最小）/ Pearson 相关性（常数列如实报错不假装零相关）
- 验收实测：导入 → 3 分析 → Markdown 报表 **0.58s**（<1 分钟 ✅），6/6 测试绿
- 只读查询护栏：`duckdb_query` 拒绝非只读语句

## 四、写作管线 demo（Phase 4）

模块 `mcpserver/material_science/writing_pipeline/`：

- bibtex：纯 Python 管理 `%APPDATA%/Lumo/writing/references.bib`（增/查/编号引用/参考文献节），幂等注入 5 条 academic 种子引用
- nature 模板：Abstract/Introduction/Results/Methods/Discussion/Data availability/References + 各节写作约束
- 一条龙 `writing_draft`：选题 → 综述（挂 [n] 引用）→ 实验设计 → 数据分析（有 CSV 直连 duckdb 三件套）→ nature 模板成稿
- 验收实测：选题到初稿 **0.11s**（9/9 测试绿），初稿含全部节 + 5 条编号引用 + 分析报表路径

## 五、硬约束核对

| 约束 | 落实 |
|------|------|
| 不破坏 SQLite RAG 检索链路 | 全量回归 358 绿（含 test_rag_pipeline/fixes/vault_integration）；新模块均为旁路，数据落 %APPDATA% 不进主仓 |
| academic 融合走独立分支 | `spec02-lumo-workbench` 独立提交；主仓已分叉，勿 force push；合入方式：在主分支 `git cherry-pick 10291308` |
| 许可白名单 + LICENSE 声明 | 16 项许可逐一登记于 `academic/LICENSES.md` 与 registry；gemmi 非白名单已警告并禁用自动调用 |

## 六、Lumo 可用工具清单（本次新增 12 个，共 22 个在位）

`academic_status` `academic_call` · `duckdb_import` `duckdb_analyze` `duckdb_query` `duckdb_report` · `graphrag_import` `graphrag_query` `graphrag_stats` · `writing_bibtex_add` `writing_bibtex_search` `writing_draft`

## 七、合入指引（给主仓维护者）

```powershell
git checkout <主仓目标分支>
git cherry-pick 10291308    # 单 commit，冲突面仅 materialscience_agent.py 注册块
```
