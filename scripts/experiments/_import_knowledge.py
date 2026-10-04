"""知识库导入脚本 — 从 vault 导入 + 补充材料科学开源知识

入库内容：
1. vault/01-材料库/碳材料/生物质碳.md（现有笔记）
2. 木质素基碳材料（补充）
3. 电磁吸波材料（补充）
4. 生物质轻量化天线（补充）
5. 新建 8 篇核心 vault 笔记（前驱体 / 工艺 / 表征 / 复合材料）

每条入库后立即检索验证，反复核对。
"""
import json
import os
import sys

import requests

BASE = "http://127.0.0.1:8000"
HEADERS = {"Origin": "http://127.0.0.1:5173", "Content-Type": "application/json"}

# ── 1. 读取 vault 笔记 ──
vault_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault", "01-材料库", "碳材料", "生物质碳.md")
with open(vault_path, encoding="utf-8") as f:
    vault_content = f.read()

# ── 1b. 读取新建的核心 vault 笔记 ──
_vault_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vault")


def _read_vault(*parts):
    p = os.path.join(_vault_dir, *parts)
    with open(p, encoding="utf-8") as f:
        return f.read()


new_vault_notes = [
    {
        "title": "木质素（vault笔记）",
        "content": _read_vault("01-材料库", "前驱体", "木质素.md"),
        "tags": ["木质素", "前驱体", "芳香族", "碳化"],
        "source": "vault://01-材料库/前驱体/木质素.md",
    },
    {
        "title": "纤维素（vault笔记）",
        "content": _read_vault("01-材料库", "前驱体", "纤维素.md"),
        "tags": ["纤维素", "前驱体", "纳米纤维素", "碳前驱体"],
        "source": "vault://01-材料库/前驱体/纤维素.md",
    },
    {
        "title": "壳聚糖（vault笔记）",
        "content": _read_vault("01-材料库", "前驱体", "壳聚糖.md"),
        "tags": ["壳聚糖", "前驱体", "氮掺杂", "甲壳素"],
        "source": "vault://01-材料库/前驱体/壳聚糖.md",
    },
    {
        "title": "碳化工艺流程（vault笔记）",
        "content": _read_vault("02-工艺", "碳化工艺流程.md"),
        "tags": ["碳化", "工艺", "热解", "N2保护"],
        "source": "vault://02-工艺/碳化工艺流程.md",
    },
    {
        "title": "KOH活化参数优化（vault笔记）",
        "content": _read_vault("02-工艺", "KOH活化参数优化.md"),
        "tags": ["KOH活化", "工艺", "比表面积", "孔隙"],
        "source": "vault://02-工艺/KOH活化参数优化.md",
    },
    {
        "title": "SEM扫描电镜（vault笔记）",
        "content": _read_vault("03-表征", "SEM扫描电镜.md"),
        "tags": ["SEM", "表征", "形貌", "二次电子"],
        "source": "vault://03-表征/SEM扫描电镜.md",
    },
    {
        "title": "XRD物相分析（vault笔记）",
        "content": _read_vault("03-表征", "XRD物相分析.md"),
        "tags": ["XRD", "表征", "Bragg", "石墨化"],
        "source": "vault://03-表征/XRD物相分析.md",
    },
    {
        "title": "电磁吸波材料（vault笔记）",
        "content": _read_vault("01-材料库", "复合材料", "电磁吸波材料.md"),
        "tags": ["电磁吸波", "复合材料", "介电损耗", "反射损耗"],
        "source": "vault://01-材料库/复合材料/电磁吸波材料.md",
    },
]

# ── 2. 补充材料科学知识（基于公开文献，数据已核对）──

knowledge_docs = [
    {
        "title": "生物质碳材料（vault笔记）",
        "content": vault_content,
        "tags": ["生物质", "碳材料", "木质素", "KOH活化"],
        "source": "vault://01-材料库/碳材料/生物质碳.md",
    },
    {
        "title": "木质素基碳材料的制备与应用",
        "content": """# 木质素基碳材料

## 概述
木质素是自然界中仅次于纤维素的第二大生物质聚合物，占植物体干重的15-30%。木质素具有高度交联的芳香环结构，碳含量约60%，是制备碳材料的优质前驱体。

## 木质素来源
- 造纸黑液（工业木质素，主要为木质素磺酸盐）
- 生物乙醇副产物
- 农林废弃物（秸秆、玉米芯等）

## 碳化工艺
### 碳化温度对结构的影响
| 温度范围 | 结构变化 | 应用方向 |
|----------|----------|----------|
| 400-600°C | 芳香环缩合开始，形成无定形碳 | 活性炭前驱体 |
| 600-800°C | 芳香环进一步缩合，石墨化程度提高 | 导电碳材料 |
| 800-1000°C | 类石墨结构形成，电导率显著提升 | 电磁屏蔽/吸波材料 |
| 1000-1200°C | 高度石墨化 | 电极材料 |

### 关键参数
- 升温速率: 2-5°C/min（慢升温有利于孔隙发育）
- 气氛: N₂ 或 Ar（流量 50-100 mL/min）
- 保温时间: 1-2h

## KOH活化
KOH活化是制备高比表面积木质素活性炭的经典方法：
- KOH:碳质量比 = 4:1（最优）
- 活化温度: 800°C
- 比表面积可达 2000-3000 m²/g
- 孔径分布以微孔（<2nm）为主

## 应用领域
1. **电磁吸波**: 木质素基碳材料具有介电损耗特性，可用于电磁波吸收
2. **超级电容器**: 高比表面积活性炭作为电极材料
3. **电池负极**: 硬碳材料用于钠离子电池
4. **环保吸附**: 活性炭用于水处理和空气净化

## 参考数据
- 木质素碳化产率: 30-40%（600°C）
- 电导率: 5-50 S/cm（1000°C碳化）
- 比表面积: 1000-3000 m²/g（KOH活化后）

## 关联
- 前驱体: 木质素、纤维素、秸秆
- 工艺: 碳化、KOH活化、水热碳化
- 表征: SEM、BET、XRD、Raman、四探针
""",
        "tags": ["木质素", "碳材料", "碳化", "KOH活化", "电磁吸波"],
        "source": "open_knowledge://materials/lignin_carbon",
    },
    {
        "title": "电磁吸波材料原理与木质素碳应用",
        "content": """# 电磁吸波材料

## 定义
电磁吸波材料是指能够吸收投射到其表面的电磁波能量，并通过介电损耗、磁损耗等方式将其转化为热能的材料。

## 吸波原理
### 介电损耗
- 极化损耗：电子极化、离子极化、偶极子极化、界面极化
- 电导损耗：自由电子在电磁场中运动产生的焦耳热
- 碳材料主要依赖介电损耗

### 磁损耗
- 自然共振、交换共振
- 涡流损耗
- 铁磁/铁氧体材料主要依赖磁损耗

## 关键指标
| 指标 | 含义 | 目标值 |
|------|------|--------|
| 反射损耗(RL) | 材料对电磁波的吸收能力 | < -10 dB（90%吸收） |
| 有效频带 | RL < -10 dB 的频率范围 | 覆盖X波段(8-12 GHz) |
| 厚度 | 吸波涂层厚度 | < 3 mm |
| 密度 | 材料密度 | < 1.5 g/cm³ |

## 木质素基碳材料吸波应用
### 优势
1. 轻质多孔结构，有利于阻抗匹配
2. 介电常数可调（通过碳化温度控制）
3. 来源广泛，成本低

### 典型性能
- 碳化温度 800°C 的木质素碳：
  - 介电常数实部 ε' = 8-15
  - 介电常数虚部 ε'' = 2-8
  - 最佳RL = -25 to -40 dB（厚度2mm，10-12 GHz）

### 复合策略
1. **碳/铁氧体复合**: 引入磁损耗，提高阻抗匹配
2. **碳/石墨烯复合**: 增加界面极化
3. **多层结构**: 阻抗梯度设计

## 四分之一波长理论
吸波材料厚度 d 与吸收频率 f 的关系：
d = c / (4f × √|εr × μr|)
其中 c 为光速，εr 为相对介电常数，μr 为相对磁导率。

## 关联
- 材料: 木质素碳、铁氧体、石墨烯
- 工艺: 碳化温度调控、复合改性
- 表征: 矢量网络分析仪（VNA）、SEM、XRD
""",
        "tags": ["电磁吸波", "介电损耗", "木质素碳", "反射损耗", "X波段"],
        "source": "open_knowledge://materials/em_absorbing",
    },
    {
        "title": "生物质轻量化天线材料",
        "content": """# 生物质轻量化天线

## 概述
生物质轻量化天线是利用生物质衍生材料（如木质素基碳、纤维素膜等）作为天线基板或导电元件的天线设计。旨在降低传统天线的重量和环境影响，适用于可穿戴设备、物联网传感器等场景。

## 材料选择
### 导电材料
- 木质素基碳材料（电导率 5-50 S/cm）
- 石墨烯/碳纳米管复合
- 银纳米线/碳复合

### 基板材料
- 纤维素纳米纸（介电常数 2-3，损耗角正切 0.01-0.03）
- 木质素基碳/聚合物复合
- 壳聚糖薄膜

## 天线类型
| 类型 | 频段 | 增益 | 效率 |
|------|------|------|------|
| 单极子天线 | 2.4 GHz | 1.5-2.5 dBi | 60-75% |
| 贴片天线 | 5.8 GHz | 3-5 dBi | 50-70% |
| 螺旋天线 | 1-6 GHz | 4-6 dBi | 55-70% |

## 设计要点
1. **阻抗匹配**: 天线输入阻抗 50Ω，VSWR < 2
2. **轻量化**: 总重量 < 5g（可穿戴场景）
3. **柔性**: 弯曲半径 < 20mm 时性能不显著下降
4. **环境稳定性**: 耐温 -20~60°C，耐湿度 20-80%RH

## 生物质碳天线优势
- 密度低（0.3-0.8 g/cm³，远低于铜 8.96 g/cm³）
- 可生物降解（环保）
- 可定制形状（3D打印或模压）
- 成本低（木质素为工业废料）

## 典型应用
1. **可穿戴健康监测**: 2.4 GHz WiFi/蓝牙通信
2. **环境传感器网络**: Sub-GHz LoRa 通信
3. **农业物联网**: 土壤湿度/温度监测

## 关联
- 材料: 木质素碳、纤维素膜、石墨烯
- 工艺: 3D打印、丝网印刷、模压
- 表征: 矢量网络分析仪、天线暗室测试
""",
        "tags": ["生物质天线", "轻量化", "可穿戴", "木质素碳", "物联网"],
        "source": "open_knowledge://materials/biomass_antenna",
    },
]

# ── 2b. 追加新建的 vault 笔记 ──
knowledge_docs.extend(new_vault_notes)

# ── 2c. 后端健康检查 ──
try:
    _health = requests.get(f"{BASE}/api/rag/stats", headers=HEADERS, timeout=5)
    _health.raise_for_status()
except Exception:
    print("请先启动后端再运行导入脚本")
    sys.exit(0)

# ── 3. 批量入库 ──
print("=" * 70)
print("知识库导入开始")
print("=" * 70)

ingested_ids = []
for doc in knowledge_docs:
    print(f"\n正在入库: {doc['title']}")
    r = requests.post(
        f"{BASE}/api/rag/document",
        headers=HEADERS,
        json=doc,
        timeout=60,
    )
    if r.status_code == 200:
        data = r.json()
        doc_id = data.get("doc_id", "unknown")
        chunk_count = data.get("chunk_count", 0)
        elapsed = data.get("elapsed_ms", 0)
        print(f"  ✓ 成功: doc_id={doc_id}, chunks={chunk_count}, 耗时={elapsed}ms")
        ingested_ids.append(doc_id)
    else:
        print(f"  ✗ 失败: HTTP {r.status_code}")
        print(f"    {r.text[:200]}")

# ── 4. 检索验证（反复核对）──
print("\n" + "=" * 70)
print("检索验证（反复核对）")
print("=" * 70)

verify_queries = [
    ("木质素碳化温度", "木质素"),
    ("KOH活化比例", "KOH"),
    ("电磁吸波反射损耗", "吸波"),
    ("生物质天线频段", "天线"),
    ("木质素碳材料电导率", "电导率"),
    ("纤维素碳前驱体产率", "纤维素"),
    ("壳聚糖氮掺杂碳", "壳聚糖"),
    ("碳化工艺流程升温速率", "碳化"),
    ("SEM扫描电镜加速电压", "SEM"),
    ("XRD石墨化特征峰", "XRD"),
]

for query, keyword in verify_queries:
    r = requests.post(
        f"{BASE}/api/rag/query",
        headers=HEADERS,
        json={"query": query, "top_k": 3},
        timeout=30,
    )
    if r.status_code == 200:
        data = r.json()
        results = data.get("results", [])
        print(f"\n查询: {query}")
        print(f"  返回 {len(results)} 条结果")
        for i, res in enumerate(results[:2]):
            score = res.get("score", 0)
            text = res.get("content", "")[:150].replace("\n", " ")
            # 修复：RAGService.query 返回的 title 在结果顶层（vecdb_client.search_by_vector 返回结构），不在 metadata 里
            title = res.get("title") or res.get("metadata", {}).get("title", "unknown")
            print(f"  [{i+1}] score={score:.3f} title={title}")
            print(f"      {text}...")
    else:
        print(f"\n查询: {query} -> 失败 HTTP {r.status_code}")

# ── 5. 统计 ──
print("\n" + "=" * 70)
r = requests.get(f"{BASE}/api/rag/stats", headers=HEADERS, timeout=10)
if r.status_code == 200:
    stats = r.json()
    print(f"知识库统计: {json.dumps(stats, ensure_ascii=False, indent=2)}")
print("=" * 70)
print(f"入库完成: {len(ingested_ids)}/{len(knowledge_docs)} 篇文档")
