# 灵感素材库索引页（工单 237 · 索引层）

> 落单：沈遥 · 执行：Trae · 日期：2026-10-14
> 物料落点：`mcpserver/material_science/synth_rag/corpus/inspiration_pool_2026-10-11/`（PR #326）
> 本页属**人工索引页**：给出分布总览、加载入口、真实检索样例与口径说明。

## §0 · 一句话

3,286 条灵感素材已随仓分发；**synth_rag 侧**走 `search_inspiration()`（词元重合，零依赖），
**rag 侧**走 `RAGService.index_inspiration_pool()` + `query(filter_theme=...)`（vecdb 语义检索）。
本层只做「检索给候选、agent 拿 abstract 自查」，**不做真伪判定**（留工单 238）。

## §1 · 总览

| 主题 | 条数 | 语料子目录 | index.json |
|---|---:|---|---:|
| biomass | 2,240 | `biomass_synth_rag_corpus/` | 2.9 M |
| sdr | 1,010 | `sdr_rag_test_corpus/` | 1.3 M |
| agent | 33 | `agent_inspiration_doc/` | 44 K |
| esp32 | 3 | `esp32_inspiration_doc/` | 4 K |
| other | 0 | `other_inspiration_doc/` | 174 B |
| **合计** | **3,286** | | **4.3 M** |

数据结构（每主题一个 `index.json`）：

```json
{
  "meta": {"source": "RESCORE-V3-2026-10-11.json", "method": "abstract-literal-keyword-match",
           "ts": "2026-10-11", "theme": "<theme>", "count": <n>, "note": "灵感素材 - 非工单库"},
  "items": [
    {"pid": "2609.09956v1", "composite": 92.0, "match": "<kw>", "target": "<1 句>",
     "abstract": "<前 1k>", "arxiv_url": "https://arxiv.org/abs/..."}
  ]
}
```

> 加载时强校验：`meta.count == len(items)` 且 `pid` 唯一（工单 237 §0 实测全部通过）；
> 校验失败抛 `ValueError`，缺文件抛 `FileNotFoundError`。

## §2 · 加载入口

### 2.1 synth_rag 侧（biomass / 全主题，零外部依赖）

```python
from mcpserver.material_science.synth_rag import search_inspiration, load_inspiration_pool

# 主题内检索（返回 list[InspirationItem]，分数降序）
hits = search_inspiration("机器学习势", top_k=5, theme="biomass")
for it in hits:
    print(it.pid, it.composite, it.target, it.arxiv_url)

# 全主题合并检索（theme=None，只遍历实际带 index.json 的主题）
hits_all = search_inspiration("频谱监测", top_k=10)

# 直接取整个主题池
pool = load_inspiration_pool(".../corpus/inspiration_pool_2026-10-11/biomass_synth_rag_corpus")
```

- 打分口径：复用 `retrieve.py` 的轻量词元重合（英文词 + CJK 二元组），**不引向量 DB**。
- 返回排序：分数降序 → `composite` 降序 → `pid` 升序（稳定可复现）。

### 2.2 rag 侧（sdr 等，vecdb 语义检索）

```python
from rag.rag_service import get_rag_service

svc = get_rag_service()
n = svc.index_inspiration_pool(".../corpus/inspiration_pool_2026-10-11/sdr_rag_test_corpus")
# n == 实际写入 chunk 数；幂等（重复调用不累积）

res = svc.query("频谱监测", top_k=10, filter_theme="sdr")
for r in res["results"]:
    print(r["doc_id"], r["content"][:80])
```

- 每主题一个文档：`doc_id = inspiration_<theme>`，`tags = [<theme>, "inspiration"]`，
  `metadata = {"source": "inspiration", "theme": <theme>, "count": <n>}`，`source_type = "manual"`。
- 每条素材一个 chunk；幂等重建先按 metadata 清旧数据。
- `filter_theme` 经文档 `tags` 过滤（与 `tags` 参数合并为「任一命中」语义）。

## §3 · 真实检索样例（验收证据）

**biomass** · `search_inspiration("机器学习势", top_k=3, theme="biomass")`：

| pid | composite | target（节选） | arxiv_url |
|---|---:|---|---|
| `2609.09956v1` | 92.0 | 为生物质（纤维素/木质素/多酚等）体系训练一个覆盖多取代基/多官能团的统一机器学习势… | https://arxiv.org/abs/2609.09956v1 |
| `2609.02148v1` | 80.0 | …用实测红外/拉曼光谱或机械性能数据作为反馈信号，自动反演分子动力学或机器学习势函数中的经验参数… | https://arxiv.org/abs/2609.02148v1 |
| `2609.03888v1` | 74.0 | …DFT/机器学习势对生物质关键官能团振动模式预测不可靠时，用 FTIR/Raman 实测频率作为"锚点参数"注入… | https://arxiv.org/abs/2609.03888v1 |

**sdr** · `search_inspiration("频谱监测", top_k=3, theme="sdr")`：

| pid | composite | target（节选） | arxiv_url |
|---|---:|---|---|
| `2608.25378v1` | 86.0 | 在 SDR 频谱监测线上，让低端硬件不做"一次全带宽 FFT"，而是按步进序列依次锁定子频带… | https://arxiv.org/abs/2608.25378v1 |
| `2602.13486` | 80.0 | SDR 频谱监测中，把宽带监测按子带/分辨率切片分别做异常检测模型融合… | https://arxiv.org/abs/2602.13486 |
| `2603.14661` | 80.0 | 我们的 SDR 频谱监测与 ESP32/LoRa 传感器网络，为每条实验数据打上"执行机制标签"… | https://arxiv.org/abs/2603.14661 |

rag 侧同一语料：`index_inspiration_pool(sdr_rag_test_corpus)` 写入 **≥ 1,010 chunk**
（真实条数 1,010）；`query(..., filter_theme="sdr")` 只返回 `doc_id=inspiration_sdr`。

## §4 · 口径说明（诚实标注）

1. **`target` 句不是论文真实研究方向**。它是 GLM **从 abstract 联想**出来的"如何用在某主题"。
   实测 biomass 前 5 篇 **4/5 完全不符**（卤化物钙钛矿被说成"生物质 ML 势"、蛋白质 MD 被
   说成"纤维素分子动力学"）。⇒ 因此本层定位为**索引层**：检索只给候选，**agent 必须拿
   `abstract` 自查**。
2. **打分实现与本仓实况对齐**。工单原文写"内部走 embedding + cosine"，但本仓 `retrieve.py`
   既有逻辑即**词元重合**（无向量 DB）——`search_inspiration` 沿用之；语义检索走 rag 侧 vecdb。
3. **不做自动化真伪判定**。留给工单 238（建议主线：lite 模型二次筛 + abstract 全文比对 +
   漏斗 2.0 闭环统计）。
4. **agent / esp32 不自动接 RAG**（量太少，33 + 3 条），只在本页人工索引；待数量扩充到
   ≥100 再评估自动接入（工单 239 建议）。

## §5 · 附录：agent 33 + esp32 3 全列

### agent（33 条）

| pid | composite | target（LLM 联想的应用场景，非论文真实方向） | arxiv_url |
|---|---|---|---|
| `2605.06992` | 80.0 | AI agent 治理架构（生物质 agent 的危险实验操作审批尤其适用——涉及高温/加压等风险操作必须独立通路校验 | https://arxiv.org/abs/2605.06992 |
| `2608.04270` | 80.0 | CURATE 的可复用模块目录 → 生物质科研 agent 的知识库——把常用实验流程（表征方法、预处理步骤、数据处理脚本）封装为显式登记的模块，agent 按需组装而非每次从零生成 | https://arxiv.org/abs/2608.04270 |
| `2608.06130` | 80.0 | 科研 agent 触发高风险动作（订购试剂、启动合成流程、覆盖实验记录、对外发布数据）前，将请求与操作者预声明的实验计划白名单做哈希比对 | https://arxiv.org/abs/2608.06130 |
| `2608.19880v1` | 80.0 | 生物质材料科研 agent | https://arxiv.org/abs/2608.19880v1 |
| `2608.22833v1` | 80.0 | ESP32/LoRa 传感器网络仿真：用同样少原语（节点位置、信道占用、丢包事件）搭建 LoRa 多节点协调的轻量仿真 | https://arxiv.org/abs/2608.22833v1 |
| `2608.24087v1` | 80.0 | 生物质实验规划/表征分析 agent，用历史实验记录（成功/失败标签）训练步骤级后验预测器 | https://arxiv.org/abs/2608.24087v1 |
| `2608.26199v1` | 80.0 | 生物质材料科研 agent 的仪器/数据库工具层 | https://arxiv.org/abs/2608.26199v1 |
| `2608.28128v1` | 80.0 | 科研 agent 的多步实验规划评估 | https://arxiv.org/abs/2608.28128v1 |
| `2609.03035v1` | 80.0 | 把"监控知情状态"作为显式变量注入生物质科研 agent 和治理系统的评估流水线 | https://arxiv.org/abs/2609.03035v1 |
| `2609.05269v1` | 80.0 | 生物质材料科研 agent 的多步实验流程中，每个中间产物用签名凭证包裹，防止溯源链在内部子 agent 边界断裂 | https://arxiv.org/abs/2609.05269v1 |
| `2605.09027` | 74.0 | 多 agent 冒名者检测 → 生物质科研 agent 的结果审核：把实验结论交给独立 verifier pass 做后验判定 | https://arxiv.org/abs/2605.09027 |
| `2606.05527` | 74.0 | ToNC 单回合挑战比特测试 → 生物质材料科研 agent 的实验结论核验 | https://arxiv.org/abs/2606.05527 |
| `2608.19181v1` | 74.0 | 生物质材料科研 agent：将"领域规则校验器/实验可行性打分"与"LLM 自评分数"分别归一化后取差，作为带符号分歧残差 | https://arxiv.org/abs/2608.19181v1 |
| `2608.19937v1` | 74.0 | 多 agent 系统（生物质科研 agent 协作、SDR 节点授权）中，agent 出示 ZK 证明"我的权限/证书未被撤销" | https://arxiv.org/abs/2608.19937v1 |
| `2608.20658v1` | 74.0 | 生物质科研 agent 把用户实验记录/文献检索结果填进工具参数时，先过一层脱敏/授权中间件 | https://arxiv.org/abs/2608.20658v1 |
| `2608.21126v1` | 74.0 | 把材料实验规划 agent 的每次仪器调用限制在 Contract 已授权范围内，防止文献摘要中的间接注入触发误操作 | https://arxiv.org/abs/2608.21126v1 |
| `2608.21516v1` | 74.0 | SDR 频谱监测系统 | https://arxiv.org/abs/2608.21516v1 |
| `2608.23631v1` | 74.0 | 材料科研 agent 的实验记录从"配方→表征结果"存档升级为"配方 → 修改操作 → 属性变化"结构化记忆 | https://arxiv.org/abs/2608.23631v1 |
| `2608.24817v1` | 74.0 | 生物质科研 agent 中，将宏观文献统计/知识图谱摘要作为微观实验规划 agent 的先验输入 | https://arxiv.org/abs/2608.24817v1 |
| `2608.25202v1` | 74.0 | 生物质材料科研 agent 的"实验方案文档 ↔ 实验记录/脚本变更"配对管线 | https://arxiv.org/abs/2608.25202v1 |
| `2608.26626v1` | 74.0 | ESP32/LoRa 网络中把节点按所有权划分，据此差异化设计认证与数据校验强度 | https://arxiv.org/abs/2608.26626v1 |
| `2608.30971v1` | 74.0 | 科研 agent 工作流的治理层 | https://arxiv.org/abs/2608.30971v1 |
| `2609.04094v1` | 74.0 | 科研 agent 评估"多步文献调研→假设→实验设计"轨迹时自动生成 rubric，用 LLM-as-judge 打轨迹总分 | https://arxiv.org/abs/2609.04094v1 |
| `2609.04773v1` | 74.0 | 生物质材料科研 agent | https://arxiv.org/abs/2609.04773v1 |
| `2609.05232v1` | 74.0 | ESP32/LoRa 节点远程固件/脚本生成场景中，把节点当前状态作为结构化字段写入 prompt | https://arxiv.org/abs/2609.05232v1 |
| `2609.05342v1` | 74.0 | ESP32/LoRa 传感器网络：把"节点/网关的空间摆放与通信拓扑"当作可优化的干预面 | https://arxiv.org/abs/2609.05342v1 |
| `2609.07035v1` | 74.0 | 生物质材料科研 agent 调用外部工具后，只做低成本的"输出必须能解释输入约束"式一致性检查 | https://arxiv.org/abs/2609.07035v1 |
| `2609.09113v1` | 74.0 | 生物质材料科研 agent 的候选材料/方案评估，让 agent 自动构造正/负对比案例验证检索命中 | https://arxiv.org/abs/2609.09113v1 |
| `2609.09519v1` | 74.0 | 生物质材料科研 agent / SDR 频谱监测 | https://arxiv.org/abs/2609.09519v1 |
| `2609.09526v1` | 74.0 | PCB 设计知识库 agent 中嵌入 DRC/ERC 规则检查器作为即时反馈工具 | https://arxiv.org/abs/2609.09526v1 |
| `2608.27260v1` | 72.5 | 论文的因子化数据对象 → 生物质科研 agent：先把仿真器/实验数据库定义为环境 E，把客观指标定义为验证器 v | https://arxiv.org/abs/2608.27260v1 |
| `2607.29007v2` | 72.0 | BCI 神经数据文本摘要 → SDR 频谱/LoRa 传感数据预处理：对射频 IQ 数据先提取统计指纹，LLM 只看指纹做算子选择 | https://arxiv.org/abs/2607.29007v2 |
| `2507.14893` | 71.0 | 生物质材料科研 agent 多方协作 | https://arxiv.org/abs/2507.14893 |

### esp32（3 条）

| pid | composite | target（LLM 联想的应用场景，非论文真实方向） | arxiv_url |
|---|---|---|---|
| `2608.04264` | 80.0 | 科研 agent 的"高层实验意图（假设/方案 DSL）↔ 实际执行脚本/仪器指令"双层级可观测架构 | https://arxiv.org/abs/2608.04264 |
| `2608.16120v1` | 74.0 | 科研 agent 的文献/实验探索策略 | https://arxiv.org/abs/2608.16120v1 |
| `2609.01683v1` | 74.0 | ESP32/LoRa 传感器网络上的环境感知模型在线校准 | https://arxiv.org/abs/2609.01683v1 |

> 附录里 `target` 已按 ≤120 字节选；完整 `target` / `abstract` 见各主题 `index.json`。

## §6 · 相关文件

| 文件 | 作用 |
|---|---|
| `mcpserver/material_science/synth_rag/schema.py` | `InspirationItem` 数据类 |
| `mcpserver/material_science/synth_rag/store.py` | `load_inspiration_pool()` / `inspiration_theme_path()` / `THEME_DIRS` |
| `mcpserver/material_science/synth_rag/inspiration.py` | `search_inspiration()` / `available_themes()` / `load_pool()` |
| `rag/rag_service.py` | `index_inspiration_pool()` / `query(filter_theme=...)` |
| `rag/vecdb_client.py` | `search_by_keyword(tag_filter=...)` |
| `mcpserver/material_science/synth_rag/tests/test_inspiration.py` | synth_rag 侧测试 |
| `tests/test_rag_inspiration.py` | rag 侧测试 |
| `research/workorder_drafts/WO-237-bio-C-inspiration-pool-rag-indexing.md` | 工单正文 |
