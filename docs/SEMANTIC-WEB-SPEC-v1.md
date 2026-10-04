# 语义网补层融合 SPEC · v1

> 制定：实验田维护者（Hermes）｜施工：Trae
> 战略锚点：陆墨知识底座缺"确定性语义推理"——现有 GRAG（summer_memory）能**查**知识（关键词/实体召回），不能**推理**知识（基于本体的规则推导）。语义网补层用 RDF/SPARQL/OWL 补这条线，让陆墨回答"木质素纳米颗粒是不是纳米材料"靠规则推、不靠 LLM 猜。
> 依据：`INTEGRATION_PLAN.md` 阶段一（语义网补层）+ knowledge 库 rdflib/oxigraph 选型
> 日期：2026-08-14

---

## 一、目标

第一个可运行闭环（M1）：

```
GRAG 五元组 → RDF 化 → rdflib 图 → 本体规则推理 → 新推三元组 → 回补查询
```

**验证问题**：GRAG 里已有 `(木质素NPs, 是, 纳米材料)`，本体里定义 `(纳米材料, rdfs:subClassOf, 材料)`。推理后应推出 `(木质素NPs, 是, 材料)`——这条 GRAG 现在推不出来，补层推出来。

---

## 二、核心设计原则（不可违背）

1. **协议无关**：语义层只认 RDF 三元组 `(S, P, O)` + SPARQL 查询。底层是 rdflib 内存图还是 pyoxigraph RocksDB，语义层不关心。
2. **先接口后实现**：Phase 0 只定 schema + 映射规则，不写任何推理逻辑。接口定死，实现随便换。
3. **底座开源，脑子 LLM**：RDF/SPARQL/OWL 是 W3C 成熟标准，不重写；LLM 只做"实体抽取 + SPARQL 生成"那部分。
4. **纯 Python 起步**：rdflib（纯 Python）+ pyoxigraph（wheel，无编译链），保证 Trae Windows 零门槛能跑。
5. **旁路接入，不破坏现有 GRAG**：只读 GRAG 五元组做 RDF 化，不动 summer_memory 的写路径。语义层挂了，GRAG 原样照跑（降级优先）。

---

## 三、接口协议（Phase 0 交付，先定死）

### 3.1 GRAG 五元组 → RDF 映射规则

GRAG 五元组 `(S, S_type, P, O, O_type)` 映射：

| 五元组字段 | RDF 侧 |
|-----------|--------|
| `S`（主语） | `lk:{slug(S)}`，URI 资源 |
| `P`（谓词） | `lk:{slug(P)}`，URI 属性 |
| `O`（宾语） | 字面量（`^^xsd:string`）或 `lk:{slug(O)}`（若 O 是实体） |
| `S_type` / `O_type` | `rdf:type lk:{slug(type)}` |

命名空间约定：
- `lk:` = `http://lumo.local/knowledge#`（本地知识命名空间）
- `rdf:` / `rdfs:` / `owl:` / `xsd:` = W3C 标准命名空间

**实体 vs 字面量判定**：`O_type` 非空 → 实体（URI）；`O_type` 为空 → 字面量。主语永远 URI。

### 3.2 本体 schema（Phase 0 定义，Phase 1 落地）

科研域轻量本体（RDFS 足够，不引入完整 OWL DL）：

```turtle
# 类层次（rdfs:subClassOf 推理链）
lk:材料        rdfs:subClassOf owl:Thing .
lk:纳米材料    rdfs:subClassOf lk:材料 .
lk:木质素纳米颗粒 rdfs:subClassOf lk:纳米材料 .
lk:水凝胶      rdfs:subClassOf lk:材料 .
lk:共熔凝胶    rdfs:subClassOf lk:水凝胶 .

# 属性（领域/值域约束，可扩展）
lk:应用于      rdfs:domain lk:材料 ; rdfs:range xsd:string .
lk:组成部分    rdfs:domain lk:材料 ; rdfs:range lk:材料 .
```

**本体是数据不是代码**：存 `ontology.ttl`（Turtle 文件），用户可继续往里面加类/属性，不碰代码。

### 3.3 三个核心接口（Phase 0 定义签名）

```python
class SemanticEngine:
    def load(self, quintuples: list[dict], ontology_ttl: str) -> None:
        """清空图 → 灌入五元组（RDF 化）+ 本体 → 跑一次推理。"""

    def query(self, sparql: str) -> list[dict]:
        """通用 SPARQL 查询，返回绑定列表。"""

    def is_a(self, entity: str, cls: str) -> bool:
        """语义判断：entity 是否是 cls 的实例/子类（走推理闭包）。"""

    def infer(self) -> list[dict]:
        """跑 RDFS/OWL-RL 推理，返回新推出的三元组列表。"""
```

**验收**（Phase 0）：`from adapters.semantic_web.engine import SemanticEngine` 可 import，四个方法签名与上表完全一致，空实现抛 `NotImplementedError` 即可。

---

## 四、目录结构

```
scratchpad/mcpserver/adapters/semantic_web/   ← 新增（照 rf_brain 模板）
├── agent-manifest.json                        ← MCP 注册
├── __init__.py
├── schemas.py                                 ← Phase 0：五元组/RDF 映射 dataclass
├── engine.py                                  ← Phase 0：SemanticEngine 骨架（四个签名）
├── rdf_mapper.py                              ← Phase 1：五元组 → rdflib 三元组
├── ontology.ttl                               ← Phase 1：科研域本体（数据，非代码）
├── reasoner.py                                ← Phase 2：RDFS/OWL-RL 推理封装
├── sparql_service.py                          ← Phase 2：SPARQL 查询服务
├── bridge.py                                  ← Phase 3：接 summer_memory + lumo_proxy
└── test_*.py                                  ← 每 phase 一个测试
```

---

## 五、分阶段施工

### Phase 0 — 接口协议 + 骨架（半天）

- **交付**：`schemas.py`（五元组 + RDF 三元组 dataclass）+ `engine.py`（SemanticEngine 四个空方法）+ `agent-manifest.json` + 空跑测试。
- **验收**：`pytest test_phase0.py` 通过；四个方法签名与 3.3 一致。

### Phase 1 — RDF 映射 + 本体（1 天）

- **交付**：`rdf_mapper.py`（3.1 映射规则落地）+ `ontology.ttl`（3.2 示例本体）+ `engine.load()` 真实实现（rdflib Graph 灌数据）。
- **验收**：喂 3 条示例五元组，`len(list(graph))` 含五元组映射 + 本体三元组；`is_a("木质素纳米颗粒", "材料")` 返回 True（走 subClassOf 链）。

### Phase 2 — 推理 + SPARQL（1 天）

- **交付**：`reasoner.py`（rdflib 的 RDFS 闭包 / OWL-RL）+ `sparql_service.py`（query 真实实现）+ `engine.query()` / `engine.infer()` 落地。
- **验收**：`infer()` 推出 `(木质素NPs, 是, 材料)`；`query()` 跑一条 `SELECT ?x WHERE { ?x rdfs:subClassOf lk:材料 }` 返回含 `lk:纳米材料` 和 `lk:木质素纳米颗粒`。

### Phase 3 — 桥接（1 天）

- **交付**：`bridge.py` 读 `summer_memory` 五元组（复用 `memory_client.get_remote_memory_client()` 或本地 `quintuple_graph`）→ 喂 SemanticEngine；在 `lumo_proxy._query_rag_standalone` 旁路加 `_query_semantic(question)`，把推理结果并进 RAG 召回。
- **验收**：`lumo_proxy` 的 RAG 召回里出现语义推理补出的新事实；semantic_web 模块卸载后 GRAG 原样照跑（降级验证）。

---

## 六、边界与铁律

| 项 | 约束 |
|----|------|
| 不破坏 GRAG | 只读 summer_memory，不改其写路径；语义层是旁路 |
| 降级优先 | semantic_web import 失败 → lumo_proxy 跳过语义召回，GRAG 照常 |
| 许可 | rdflib BSD-3 / pyoxigraph Apache-2.0，均可合入；AGPL 主仓兼容 |
| 不做双写 | 推理结果不入 GRAG 存储（避免污染），只做查询时合并 |
| 本体可扩展 | ontology.ttl 是数据，用户后续加类不碰代码 |

---

*v1 由实验田维护者制定，照射频大脑 SPEC（RF-BRAIN-SPEC-v1.md）同款"先接口后实现"骨架。*
