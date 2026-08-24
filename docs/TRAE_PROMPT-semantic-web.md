# 任务：语义网补层施工（照 SPEC 写代码）

你是 scratchpad 项目的融合工程师。scratchpad 是个人 AI 助手 monorepo（AGPL v3），当前在给陆墨（AI 助手）补"确定性语义推理"能力。

## 背景（为什么做）

陆墨现有知识底座是 GRAG（`summer_memory/` 目录），它靠 LLM 从对话抽三元组/五元组存图，查询走 `memory_client.RemoteMemoryClient` 的关键词/实体召回。**问题**：GRAG 只会"查"，不会"推理"——比如它存了 `(木质素NPs, 是, 纳米材料)`，但你问"木质素NPs 是不是材料"，它推不出来（因为缺"纳米材料 → 材料"这条 subClassOf 链的规则推理）。

语义网补层用 RDF/SPARQL/OWL 补这条线：把 GRAG 五元组映射成 RDF，加一个科研域本体，用规则推理补全缺失的传递关系。答案靠规则推，不靠 LLM 猜。

## 输入

1. **SPEC**：`scratchpad/docs/SEMANTIC-WEB-SPEC-v1.md`（这是施工图纸，先读它，接口和映射规则都定死了）
2. **现有 GRAG 代码**：`scratchpad/summer_memory/`（重点看 `quintuple_graph.py` 五元组结构、`memory_client.py` 的 `get_remote_memory_client()`、`quintuple_rag_query.py`）
3. **RAG 召回入口**：`scratchpad/apiserver/routes/lumo_proxy.py` 的 `_query_grag()` / `_query_rag_standalone()`
4. **参考模板**：`scratchpad/mcpserver/adapters/rf_brain/`（射频大脑已按同款"先接口后实现"骨架做完，照它的目录结构和 agent-manifest.json 格式）

## 你的任务

严格按 SPEC 的"五、分阶段施工"走，Phase 0 → 3，每个 Phase 做完跑对应 `test_phase*.py`，过了再进下一个。

关键点：
- **Phase 0 只定骨架**，`SemanticEngine` 四个方法（`load/query/is_a/infer`）签名必须和 SPEC 3.3 完全一致，空实现抛 `NotImplementedError`。
- **Phase 1 的映射规则**严格照 SPEC 3.1：主语永远 URI，`O_type` 空→字面量、非空→实体 URI。本体存 `ontology.ttl`（Turtle），不是硬编码。
- **Phase 2 用 rdflib 自带推理**（`rdflib.plugins.reasoner` 或手写 RDFS subClassOf 闭包），不要自己发明推理算法。
- **Phase 3 是旁路接入**：只读 summer_memory 五元组，不改它的写路径。在 lumo_proxy 里加 `_query_semantic()`，把语义推理结果并进 RAG 召回，但**必须 try/except 包裹**——semantic_web 模块挂了，GRAG 原样照跑。

## 依赖

- `rdflib`（BSD-3，纯 Python）—— 主依赖，装它
- `pyoxigraph`（Apache-2.0，wheel）—— 可选持久化后端，Phase 1-2 先用 rdflib 内存图跑通，pyoxigraph 留到需要 RocksDB 持久化时再接，**不要** M1 就硬上

## 硬约束

1. **不破坏现有 GRAG**：summer_memory 目录一个文件都不许改，只能读。
2. **纯 Python**：不引入 C 编译链，保证 Windows 零门槛能跑。
3. **旁路降级**：所有 semantic_web 调用点都要 try/except，挂了不影响主链路。
4. **先接口后实现**：接口签名（SPEC 3.3）一个字段都不许动，改了打回。
5. **测试先行**：每个 Phase 先写 test，再写实现，test 过了才算交付。
6. **中文注释 + 务实**：不吹，不写"业界领先"这类废话。Python 用 ruff 风格（`python -m ruff check .`）。

## 输出

- 代码落 `scratchpad/mcpserver/adapters/semantic_web/`
- 每个 Phase 完成后，报告：改了哪些文件 + 测试结果 + 验收标准是否达成
- 最后跑一遍 `python -m pytest mcpserver/adapters/semantic_web/ -v`，贴全绿结果
