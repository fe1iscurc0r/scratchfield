# ChemMCP 授粉报告

> 2026-08-29 · 来源：OSU-NLP-Group/ChemMCP（Apache-2.0，71★，扫货日报 8/29 Top2）
> 勘察：README + src/chemmcp/tools/ 工具清单 + pyproject
> 定位：化学工具 MCP 工具集——给 LLM/AI 助手挂上分子分析与反应合成能力（源自 ChemToolAgent）

## 一句话

ChemMCP 把"AI 助手 + 化学工具"做成即插即用：SMILES 处理、性质预测、反应产物预测、专利/安全检索全工具化，MCP 或 Python 双模式接入。材料科研唯一直接对口的 MCP 项目。

## 工具清单（分类）

| 分类 | 工具 | 对我们的用途 |
|------|------|-------------|
| 分子 | smiles_canonicalization / smiles2cas / smiles2iupac / smiles2formula / molecule_smiles_check | 木质素/生物质分子结构规范化、CAS 号检索 |
| 分子性质 | bbbp_predictor / solubility_predictor / hiv_inhibitor_predictor / molecule_weight / functional_groups | 性质预测管线参照（注意：偏药物化学，材料性质需自建） |
| 分子生成 | molecule_generator / molecule_modifier / molecule_visualizer | 分子编辑/可视化（水凝胶前体设计可参考） |
| 反应 | reaction_smiles_check / side_effect_predictor | 反应产物/副产物预测（合成路线规划） |
| 通用 | web_search / patent_check / safety_check / python_executor | 专利检索 + 安全审查（材料合成实验直接有用） |

## 可授粉点

| # | 点 | 流向 | 价值 |
|---|-----|------|------|
| 1 | **模块化 schema**（加工具=写一个 Python 文件，统一接口，自动文档） | mcpserver 工具规范 | 与 mcpserver 的 manifest.json 模式同构，工具注册/文档生成惯例可直接对齐 |
| 2 | **safety_check 理念** | 材料合成安全 | 木质素 NPs→水凝胶/共熔凝胶实验前安全审查工具化（呼应其伦理声明） |
| 3 | **SMILES 工具链** | 材料知识库管线 | 生物质分子结构检索层可借鉴（CAS/分子式/SMILES 互转） |
| 4 | **双模式接入**（MCP server + 独立 Python import） | mcpserver 设计 | 同一工具集两种暴露面，数据处理直接用 Python，agent 走 MCP——与 fastmcp 惯例一致 |
| 5 | **专利检索工具** | 陆墨科研 | 材料专利查新（合成路线 RAG 的补充工具） |

## 差距/注意

- 性质预测工具偏**药物化学**（BBBP 血脑屏障/HIV），对生物质材料（木质素/水凝胶）无直接模型——需要的是**材料描述符预测**（MOF 吸附、聚合物性质），ChemMCP 只提供管线骨架。
- 依赖较重（RDKit 系），云服/天选7 安装需评估。
- 星低(71★)但学术背书（OSU NLP Group），工具质量可靠。

## 落地建议

- P0：把 ChemMCP 的**工具 schema 惯例**（统一输入输出 + 自动文档 + 双模式）收进 mcpserver 工具编写规范
- P1：材料侧自建描述符预测工具时，复用其模块化模式（smiles2cas/smiles2formula 这类纯转换工具可先接）
- P1：safety_check 思路落到木质素/水凝胶实验安全清单（陆墨线）
- 完整 clone 已在 github_haul/ChemMCP，Trae 可读码实现
