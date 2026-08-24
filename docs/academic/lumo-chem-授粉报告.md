# Lumo 化学/药物库授粉报告（E-01）

> **工单**: E-01  
> **日期**: 2026-08-23  
> **背景**: 沈遥 Lumo 科研库（W-09 封装 4 库：coolprop/chemformula/tespy/slices），本工单为 academic MODEL_INTERFACE 体系扩展化学/药物库。  
> **调研库**: chembl_webresource_client、oddt、Indigo、scikit-fingerprints  
> **契约规范**: 统一返回 `{ok, ...data, source}`；参数非法抛 `ValueError`；依赖缺失抛 `AcademicDependencyError`（含 pip install 提示）

---

## 一、融合层级总表

| 库 | 许可 | 层级标注 | 理由 |
| --- | --- | --- | --- |
| chembl_webresource_client | Apache-2.0 | **MCP 候选** | 纯网络客户端，零本地编译依赖，返回结构化字典，完全符合 MCP 契约；分子/靶点/活性数据源价值高 |
| oddt | BSD-3 | **只参考** | 硬依赖 OpenBabel 或 RDKit（两者均重型 C++ 编译库），本地编译环境强耦合；源码参考 QSAR 建模思路 |
| Indigo | Apache-2.0 | **只参考** | 官方分发为预编译二进制（`pip install epam.indigo`），wheel 含原生 so 文件，非纯 Python；源码参考反应/MOL处理逻辑 |
| scikit-fingerprints | MIT | **MCP 封装候选** | 纯 Python + RDKit（已纳入 Lumo 生态），统一 `.transform()` 接口，sklearn 兼容，依赖链可接受；MIT 许可与 Lumo 兼容 |

---

## 二、逐库定位 + 许可 + 核心 API

### 1. chembl_webresource_client（Apache-2.0）

**定位**: ChEMBL 数据库官方唯一 Python 客户端（EBI 出品）。将 ChEMBL REST API 封装为类 Django QuerySet 的懒求值接口，网络透明（自动缓存文件系统中），调用方无需写 SQL、无需懂 REST 协议。

**许可**: Apache-2.0，商业友好。

**核心 API（README + demo notebook 确认）**:
- 入口: `from chembl_webresource_client.new_client import new_client`
- 资源端点: `new_client.molecule` / `target` / `activity` / `similarity` / `assay` / `image` 等
- 链式查询: `.filter(...).only(['field1','field2'])` → 惰性，求值时才发网络请求
- 取值: `.get(chembl_id)` 单条；直接迭代遍历
- 可用过滤器（与 Django ORM 同款）: `exact / iexact / contains / icontains / in / gt / gte / lt / lte / startswith / range / isnull / regex`
- 相似性搜索: `new_client.similarity.filter(smiles="...", similarity=70)`（70 = 70% Tanimoto）
- 图像: `new_client.image.get('CHEMBL25', format='svg')`

**运行依赖**:
```
urllib3
requests>=2.18.4
requests-cache~=1.2
easydict
```
无重型 C++ 依赖，pip 直装，**轻量级**。

---

### 2. oddt — Open Drug Discovery Toolkit（BSD-3）

**定位**: 模块化药物发现综合工具包（对接、虚拟筛选、打分函数重评分、QSAR 建模）。支持 OpenBabel 和 RDKit 双后端，通过 `ODDT_TOOLKIT` 环境变量切换，`toolkit` 属性统一访问。

**许可**: BSD-3-Clause，商业友好。

**核心 API**:
- `import oddt; oddt.toolkit` → 当前激活后端（ob 或 rdk）
- 分子读取: `oddt.toolkit.read_mol('mol.sdf')` / `from_smiles(smi)`
- 分子操作: 构象生成、能量最小化、加氢、去除配体等
- 打分函数: `oddt.scoring.functions`（NNScore、RFScore、PLECscore 等）
- 分子指纹: `oddt.fingerprints`（ECFP、MACCS 等）
- 相互作用指纹: `oddt.interactions`（2D 相互作用指纹）
- 全局随机种子: `oddt.random_seed(n)`

**运行依赖**:
```
numpy>=1.12, scipy>=0.19, scikit-learn>=0.18, joblib>=0.10, pandas>=0.19.2
# 硬性二选一:
OpenBabel (3.0+)  或  RDKit (2018.03+)
# 可选:
skimage>=0.12.3  # 仅表面生成
```
**重型依赖**：OpenBabel/RDKit 均为 C++ 编译库，conda 或源码编译安装，耦合重。

---

### 3. Indigo（Apache-2.0）

**定位**: EPAM 出品通用 cheminformatics 引擎，跨 .NET/Java/Python/R/WASM 多语言绑定，支持 Bingo（数据库搜索）、Indigo（分子/反应处理）两大产品线。Python 包名为 `epam.indigo`。

**许可**: Apache-2.0。

**核心 API**:
- `indigo.indigo()` 单例
- `indigo.loadMolecule(smiles/inchi/cml)` → 分子对象
- `indigo.loadReactionFromSmiles(smi)` → 反应对象
- `indigo.canonicalSmiles()` / `indigo.aromaticSmiles()`
- `indigo.saveMoleculeToFile()`、`indigo.render()`（图像）
- 指纹: `indigo.loadFingerprintFromSDFile()`、`indigo.createFingerprint()`
- 反应操作: `reaction.automap()`（自动映射）、`reaction、香工业化`
- 数据库搜索（Bingo）: `indigo.dbConnect()` → SQL式化学检索

**运行依赖**: 官方分发为预编译二进制 wheel（含原生 `.so` / `.dylib`），`pip install epam.indigo` 直装但含 C++ 引擎，非纯 Python 包。

---

### 4. scikit-fingerprints（MIT）

**定位**: 分子指纹 + 化学信息学 ML 管线库，sklearn 兼容。提供 30+ 指纹（ECFP/MACCS/Avalon/PubChem 等）、30+ 分子过滤器（Lipinski/PAINS/REOS）、14 种相似度度量、适用性域检验，与 sklearn `Pipeline` / `GridSearchCV` 无缝集成。

**许可**: MIT，最宽松。

**核心 API**:
```python
from skfp.fingerprints import ECFPFingerprint, MACCSFingerprint

fp = ECFPFingerprint(count=True, radius=2)   # count=True 返回环形计数 fingerprint
X = fp.transform(smiles_list)                # list[str] → numpy array / sparse matrix

# 完整 sklearn 管线
from sklearn.pipeline import make_pipeline, make_union
from skfp.preprocessing import MolFromSmilesTransformer
pipeline = make_pipeline(
    MolFromSmilesTransformer(),              # SMILES → RDKit mol
    make_union(ECFPFingerprint(), MACCSFingerprint()),
    RandomForestClassifier()
)
pipeline.fit(X_train, y_train)
```

主要 fingerprint 类（均继承统一接口）:
- `ECFPFingerprint` / `ECFP4Fingerprint`（圆形指纹）
- `MACCSFingerprint`、`AvalonFingerprint`、`PubChemFingerprint`
- `rdkitfp`（RDKit fingerprint）、`topological`/`electrotopological`
- `MordredFingerprint`（调用 mordredcommunity 计算 2D 描述符指纹化）
- ` AtypicalFingerprint`（非典型结构指纹）
- 相似度/距离: `skfp.metrics` / `skfp.distances`

**运行依赖**:
```
rdkit>=2023.9.6
mordredcommunity>=2.0.0
descriptastorus>=2.0.0
e3fp>=1.2.6
huggingface_hub>=0.20.0
joblib>=1.0.0
numpy>=1.26.4
pandas>=1.5.3
scikit-learn>=1.6.0
scipy>=1.12.0
tqdm>=4.0.0
```
**重型核心依赖**: `rdkit`（C++ 编译库，但已在 Lumo 生态中）。其余为纯 Python 包。

---

## 三、封装建议：接口命令草案

> 参照 `/home/ubuntu/scratchpad/docs/academic/MODEL_INTERFACE.md` 格式：
> `命令 | 参数 | 返回`
> MCP 注册名 `academic`，`scan_and_register_mcp_agents` 自动发现。

### ▶ chembl_webresource_client（推荐 MCP 封装）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `chembl_check` | — | `{available: bool, version?}` |
| `chembl_molecule_search` | `query`(str, 名称或同义词), `topk=10`(int) | `{results: [{chembl_id, pref_name, molecule_type, ...}], source}` |
| `chembl_molecule_by_id` | `chembl_id`(str, 如 CHEMBL25) | `{chembl_id, pref_name, molecule_structures, synonyms, ...}` |
| `chembl_similarity` | `smiles`(str), `similarity`(int 0-100, 默认 70), `topk=20`(int) | `{results: [{chembl_id, pref_name, similarity}], source}` |
| `chembl_target_search` | `query`(str, 基因名/靶点名), `organism?`(str) | `{results: [{target_chembl_id, pref_name, target_type, organism}], source}` |
| `chembl_activity` | `target_chembl_id`(str), `standard_type?`(str, 如 IC50/Ki), `topk=100`(int) | `{results: [{molecule_chembl_id, pchembl_value, activity_type, assay_id}], source}` |

**说明**: 所有端点均为懒求值，封装层强制 `.only()` 限制字段并触发一次求值（`.all()` 遍历），控制数据量；结果字典化。依赖缺失时 `AcademicDependencyError: chembl_webresource_client 未安装：pip install chembl_webresource_client`。

---

### ▶ scikit-fingerprints（推荐 MCP 封装）

| 命令 | 参数 | 返回 |
| --- | --- | --- |
| `skfp_check` | — | `{available: bool, version?}` |
| `skfp_fp` | `smiles_list`(list[str]), `fp_type`("ECFP"/"MACCS"/"Avalon"/"rdkit"/"topological", 默认ECFP), `count`(bool, 默认False, True返回计数向量), `radius`(int, 默认2, 仅ECFP) | `{fingerprints: list[list[int]] 或 list[scipy.sparse], shape: (N, bits), fp_type, source}` |
| `skfp_filters` | `smiles_list`(list[str]), `filter_names`(list[str], 如 ["LipinskiRuleOf5","PAINS"]) | `{passed: list[bool], failed_counts: dict}` |
| `skfp_similarity` | `smiles_list`(list[str]), `metric`("tanimoto"/"dice"/"cosine", 默认tanimoto) | `{similarity_matrix: np.ndarray, source}` |

**说明**: `skfp_fp` 基于 `skfp.fingerprints` 子类，`skfp_filters` 调用 `skfp.filters`。`MolFromSmilesTransformer()` 由封装层内部调用，上层只接触 SMILES list。依赖缺失时 `AcademicDependencyError: scikit-fingerprints 未安装：pip install scikit-fingerprints`（rdkit 已纳入 Lumo 生态，若缺失则提示 `pip install rdkit`）。

---

## 四、运行依赖汇总对照

| 库 | pip 安装名 | 核心重型依赖 | 纯 Py 依赖 | 重依赖处理策略 |
| --- | --- | --- | --- | --- |
| chembl_webresource_client | `chembl_webresource_client` | 无 | `requests`, `urllib3`, `requests-cache`, `easydict` | **无重依赖**，MCP 直接封装 |
| oddt | `oddt` | OpenBabel **或** RDKit（编译库） | `numpy`, `scipy`, `sklearn`, `pandas`, `joblib` | **不封装**，仅源码参考（硬依赖链过重） |
| Indigo | `epam.indigo` | C++ 二进制引擎（wheel 含 so/dylib） | 无纯 Py 替代 | **不封装**（非纯 Python 包，含原生二进制） |
| scikit-fingerprints | `scikit-fingerprints` | `rdkit`（C++ 编译库） | `mordredcommunity`, `descriptastorus`, `e3fp`, `numpy`, `pandas`, `sklearn`, `scipy`, `joblib`, `tqdm` | **MCP 封装候选**；rdkit 已纳入 Lumo 生态（thermo/SLICES 链已有） |

---

## 五、决策摘要

| 库 | 层级 | 封装优先级 | 理由 |
| --- | --- | --- | --- |
| chembl_webresource_client | **MCP** | ⭐⭐⭐ 高 | 零重型依赖，网络即插即用，数据源覆盖 200 万化合物/150 万活性数据，MISSING PIPELINE 缺口直接填补 |
| scikit-fingerprints | **MCP** | ⭐⭐⭐ 高 | MIT 许可，rdkit 已在 Lumo 生态，指纹计算是 QSAR ML 管线基础，接口极简（`.transform()`） |
| oddt | 只参考 | ⭐ 参考 | BSD-3，但硬依赖 OpenBabel/RDKit 编译库，接入成本高；源码中 QSAR 建模思路可移植到 scikit-fingerprints 实现 |
| Indigo | 只参考 | ⭐ 参考 | Apache-2.0 许可优，但官方分发含二进制引擎，非纯 Python；反应处理/MOL 渲染逻辑参考 |

**推荐 MCP 封装顺序**: ① `chembl_webresource_client` → ② `scikit-fingerprints`（两库均为纯 Python / 轻依赖，可并行进行）。
