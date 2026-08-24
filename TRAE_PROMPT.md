# 任务：scratchpad 知识底座预处理

你是 scratchpad 项目的融合工程师。scratchpad 是个人 AI 助手 monorepo（AGPL v3），
当前握着三张牌：GRAG（图检索，继承自 NagaAgent）、RAG、Obsidian 笔记库。
目标：拓展 AI agent 广度，不局限 LLM。

## 输入

GitHub 私库 fe1iscurc0r/scratchpad-knowledge，34 个项目，两个目录：

academic/（16 个科学计算冷门包）
- thermo/tespy/pycalphad/Clapeyron.jl/CoolProp（热力学）
- PyXtal/SLICES/gemmi（晶体/材料结构）
- ChemFormula/hyalite/AffineGaps（化学式解析/序列比对）
- WaveBench/rp2daq/hololinked（仪器控制/数据采集）
- Pynite/FEMcy（有限元）

knowledge/（20 个非 LLM 拓广包）
- graphrag/LightRAG/llm-graph-builder（GraphRAG 对照）
- rdflib/oxigraph/terminusdb/neosemantics/trustgraph（语义网/本体论）
- Nucleoid/OpenReason/business_rules_reasoning（逻辑推理引擎）
- sift/second-brain/kb-arena（混合检索）
- obsidian-skills/khoj/quartz/siyuan（Obsidian 生态）
- FalkorDB（SSPL，图数据库，仅架构参考）/ corese-core（无LICENSE，仅参考）

## 你的任务（每个项目输出一节）

1. 读 README + 核心目录 + 关键入口文件，搞清楚它到底做什么
2. 判断融合层级（五选一）：
   - MCP：能独立跑成 MCP server，接进 scratchpad/mcpserver/
   - Skill：本质是工作流/知识，写成 .md 技能进 skills/
   - 融合参考：完整架构但非即插即用，只提炼可借鉴设计
   - 耦合：完整源码合入 scratchpad 作为子项目
   - 基础设施：独立部署（DB/服务），不进主仓
3. 标注运行依赖（GPU？付费 API？特定平台？）
4. 给出融合价值：能解决 scratchpad 哪个具体痛点

## 重点方向（按这个优先级）

1. **语义网补层**（rdflib/neosemantics/oxigraph）— GRAG 缺语义推理，这层是"确定性知识"
2. **逻辑引擎**（Nucleoid/OpenReason）— LLM 之外的第二条推理线
3. **混合检索**（sift/second-brain/kb-arena）— 跳出纯向量，BM25+重排
4. **Obsidian 桥接**（obsidian-skills）— agent 直接读写笔记库
5. **热力学/材料**（thermo/CoolProp/SLICES 等）— Lumo 材料库的地基

## 输出格式（每个项目一节，200 字内，中文）

### <项目名>
- 定位：一句话
- 融合层级：MCP / Skill / 融合参考 / 耦合 / 基础设施
- 运行依赖：<GPU/付费API/平台/无>
- 价值判断：<解决什么痛点 / 纯参考>
- 可借鉴点：<3 条以内，具体到模块或设计模式>

## 硬约束

- 只读分析，不 clone 新仓库，不执行 git 操作，不推代码
- 源码已在 fe1iscurc0r/scratchpad-knowledge 里，直接读即可
- 许可不是 MIT/BSD/Apache-2.0/GPLv3/AGPLv3 的项目，标"许可存疑"即可
- 输出用中文，务实，不吹
