# 阶段五 A档 · 材料底座 SPEC · v1

> 制定：实验田维护者（Hermes）｜施工：Trae
> 依据：INTEGRATION_PLAN.md 阶段五 A档
> 战略锚点：陆墨缺"确定性材料计算"——现有 LLM 靠猜，给陆墨装分子式解析 / 分子量计算 / 组成算术，让材料专业问题的答案有据可查，不是 LLM 幻觉。

---

## 一、目标与范围

**交付两个 Python 模块，合入 `scratchpad/mcpserver/adapters/`**：

| 模块 | 源码来源 | 能力 |
|------|----------|------|
| `chem_adapter/` | `scratchpad-knowledge/academic/ChemFormula/`（Apache 2.0）| 分子式解析 / 分子量 / 质量分数 / 组成算术 |
| `bio_adapter/` | `scratchpad-knowledge/academic/AffineGaps/`（Apache 2.0）| 序列比对（Needleman-Wunsch / Smith-Waterman） |

**不涉及**：热力学物性（thermo）、相平衡（pycalphad）、流体物性（CoolProp）、晶体结构（PyXtal/gemmi）——这些归 B/C 档，另阶段推进。

**陆墨接入点**：`apiserver/routes/lumo_proxy.py` 的 `_query_rag_standalone` 下新增 `_query_chem` 旁路（与语义网补层 Phase 3 同款模式），在 RAG 召回结果里注入化学计算结果。

---

## 二、ChemAdapter 详细规格

### 2.1 源码复用策略

直接复用 `scratchpad-knowledge/academic/ChemFormula/src/chemformula/` 全套（含 `elements.py` 原子量数据），不重写。
- `elements.py`：原子量 / 价态 / 元素符号，纯数据文件，进入 `chem_adapter/data/`。
- `chemformula.py`：`ChemFormula` 主类，进入 `chem_adapter/core.py`。
- `config.py`：配置，进 `chem_adapter/config.py`。
- `__init__.py`：导出接口，进 `chem_adapter/__init__.py`。

### 2.2 核心接口（必须保留的方法签名）

```python
from chem_adapter import ChemFormula

cf = ChemFormula("H2SO4")          # 解析分子式（含电荷支持）
cf.element                          # → ChemFormulaDict: {"H": 2, "S": 1, "O": 4}
cf.formula_weight                   # → float: 分子量（单位 g/mol）
cf.mass_fraction                    # → ChemFormulaDictFloat: 各元素质量分数
cf.hill_formula                     # → ChemFormulaString: 希尔排序（HCNO优先）
cf.sum_formula                      # → ChemFormulaString: 实验式
str(ChemFormula("CH3COOH") + ChemFormula("C2H5OH"))  # → "C3H8O" 组成相加
ChemFormula("H2O") * 3              # → "H6O3" 计量乘法
```

### 2.3 原子量数据（elements.py）

**不修改原始数据文件格式**。进入 `chem_adapter/data/elements.py`，原子量按 IUPAC 2024 标准。

### 2.4 依赖策略

- `casregnum`：可选（用于 CAS 注册号解析）。主流程不依赖，装了增强，不装降级。
- 其余全部 stdlib：`re`、`warnings`、`typing`。

---

## 三、BioAdapter 详细规格

### 3.1 源码复用策略

直接复用 `scratchpad-knowledge/academic/AffineGaps/affine_gaps.py`（单文件 41KB），进入 `bio_adapter/align.py`。

### 3.2 核心接口

```python
from bio_adapter import needleman_wunsch_gotoh_alignment, smith_waterman_gotoh_alignment

# 全局比对（Needleman-Wunsch，affine gap penalty）
align1, align2, score = needleman_wunsch_gotoh_alignment("GATTACA", "GCATGCU")
# align1 = "G-ATTACA"  align2 = "GCAT-GCU"  score = 3

# 局部比对（Smith-Waterman，affine gap penalty）
align1, align2, score = smith_waterman_gotoh_alignment("GATTACA", "GCATGCU")

# Numba 加速：自动检测，有则加速，无则纯 Python 回退
```

### 3.3 依赖策略

- `numpy`：必须（DP 矩阵必须）
- `numba`：可选，有则 JIT 加速，无则纯 Python
- `colorama`：可选（CLI 彩色输出，不影响库调用）

---

## 四、陆墨接入（旁路模式）

与语义网补层 Phase 3 同款架构：

```
lumo_proxy._query_rag_standalone()
    ├── _query_grag()              ← 现有 GRAG 召回
    ├── _query_local_rag()         ← 现有向量召回
    ├── _query_semantic()          ← 语义网推理（已落地）
    └── _query_chem()              ← [新增] 化学计算旁路
```

`_query_chem(question)` 逻辑：
1. 从问题文本抽化学式（正则：`[A-Z][a-z]?[0-9]*` 重复）
2. 对每个化学式调 `ChemFormula` 计算 `formula_weight` / `element` / `mass_fraction`
3. 格式化结果文本，拼进 RAG 召回节

**降级铁律**：任何计算异常 → 返回空字符串，不影响主链路。

---

## 五、分阶段施工

### Phase A1：ChemAdapter 骨架（只搭不实现）

- 创建目录 `mcpserver/adapters/chem_adapter/`
- 复制 `elements.py` → `data/elements.py`（不修改数据）
- 复制 `chemformula.py` → `core.py`（仅重命名，零修改）
- 复制 `config.py` → `config.py`
- 创建 `__init__.py`：导出 `ChemFormula`、`ChemFormulaString`、`ChemFormulaDict`
- **测试**：`python -c "from mcpserver.adapters.chem_adapter import ChemFormula; print(ChemFormula('H2SO4').formula_weight)"`（预期输出 ~98）

### Phase A2：BioAdapter

- 创建目录 `mcpserver/adapters/bio_adapter/`
- 复制 `affine_gaps.py` → `align.py`
- 创建 `__init__.py`：导出三个核心函数
- **测试**：`python -c "from mcpserver.adapters.bio_adapter import needleman_wunsch_gotoh_alignment; a,b,s=needleman_wunsch_gotoh_alignment('GATTACA','GCATGCU'); print(s)"`（预期 output 3）

### Phase A3：陆墨接入

- 在 `lumo_proxy.py` 的 `_query_rag_standalone` 添加 `_query_chem` 旁路
- 参照 `_query_semantic` 的 try/except 降级模式
- **测试**：在有化学式问题的 RAG 查询中验证输出含计算结果

### Phase A4（可选，Numba 加速）

- 安装 `numba`：`pip install numba`
- 验证 `HAS_NUMBA = True`，确认 JIT 路径生效

---

## 六、验收标准

| 标准 | 验证 |
|------|------|
| `ChemFormula('H2SO4').formula_weight` ≈ 98.072 | A1 测试通过 |
| `ChemFormula('C6H12O6').hill_formula` → C6H12O6 | A1 测试通过 |
| `needleman_wunsch_gotoh_alignment('GATTACA','GCATGCU', alphabet='ACGTU', match=3, mismatch=-2, gap_opening=-3, gap_extension=0)` = 3 | A2 测试通过（需显式 DNA 字母表参数；默认蛋白字母表不含 U） |
| `lumo_proxy._query_chem('H2SO4 分子量')` 返回含计算结果 | A3 集成测试 |
| 无化学式问题时返回空字符串，不报异常 | A3 降级测试 |
| `numba` 装则 JIT 路径生效，不装则纯 Py 回退 | A4（可选）|

---

## 七、依赖修正

| 包 | SPEC 原标注 | 实际情况 | 处理 |
|----|------------|----------|------|
| `casregnum` | 可选 | **必须**（`core.py` 顶层无条件 `import casregnum`） | A1/A2/A3 之前必须装 |
| `numpy` | 必须 | 必须 | A2 之前必须装 |
| `numba` | 可选 | 可选 | A4（可选） |
| `colorama` | 可选 | 可选 | CLI 彩色输出，不影响库调用 |

---

## 八、风险

| 风险 | 缓解 |
|------|------|
| `elements.py` 含 118 个元素数据，重复制可能与上游脱钩 | 数据文件独立存放于 `data/`，升级时整体替换 |
| `casregnum` 是硬依赖未在 SPEC 标注 | 已补入本版本第七节依赖修正表 |
| A2 默认蛋白字母表不含 U，SPEC 验收项有误 | 已修正为「显式 DNA 字母表参数」版本 |
| 多进程环境下 numpy 全局解释器锁 | 比对是计算密集非 IO，GIL 影响可接受 |
