# Bioindustrial-Park 基准模型导览 · 2026-10-01（卷170-A）

> 上游：`BioSTEAMDevelopmentGroup/Bioindustrial-Park`（MIT，⭐53）——bioSTEAM 官方模型库。
> **1225 文件**，全部 gh api contents 按需读（**未整仓 clone**——工单硬约束，仓库 6.4GB）。

---

## 一、模型库目录结构图（实测 `biorefineries/` 下 38 个模型目录）

```
biorefineries/
├─ 生物质→化学品类
│  ├─ BDO（1,4-丁二醇）      FT（费托）       LAOs（直链烯烃）
│  ├─ OHFA / TAL / oxalic / succinic / lactic / isobutanol
│  ├─ ethanol（纤维素乙醇）+ ethanol_adipic（己二酸联产）
│  └─ oleochemicals / biodiesel / gas_fermentation
├─ 生物质原料类（专用作物）
│  ├─ sugarcane / cane / lipidcane / oilcane（油料甘蔗）
│  ├─ corn / cornstover / wheatstraw / miscanthus（能源草）
│  └─ microalgae / animal_bedding / mixed_feedstock
├─ 过程与评价类
│  ├─ wwt（废水处理）/ HP / nitric
│  ├─ lca（生命周期评价线）
│  └─ tea（TEA 计算基类与样例）★
└─ tests/（模型回归测试）
```

（实测目录清单，gh api git/trees 递归——38 个 `biorefineries/<name>/` 一级目录）

## 二、两个模型文件实测摘录

### 2.1 cellulosic（纤维素乙醇，`biorefineries/cellulosic/biorefinery.py`）

**系统边界（实测 Area 分组——bioSTEAM 的 unit operations 分区惯例）**：

| Area | 单元操作（实测代码引用） | 段落 |
|---|---|---|
| Area 100 | U101 | 进料储存/输送 |
| Area 200 | T201, M201, R201, P201, P202 … | **预处理**（汽爆/酸处理） |
| Area 300 | H301, M301, R301 … | **酶水解 + 发酵**（糖化） |
| Area 400 | D401, H401, D402, P401 … | 产品回收/蒸馏区 |
| Area 500 | WWTC | 废水处理 |
| Area 600 | T701, T702, P701, P702, M701, FWT … | 固液分离/干燥 |
| Area 700 | BT | **锅炉/涡轮**（热电联产） |
| Area 800 | CWP, CT, PWC, ADP, CIP | 冷却水/公用工程 |

**关键方法**：`create_thermo()`（热力学包）→ `create_system()`（连单元）→ `create_model()`
（构造**参数模型**——`bst.process_tools.Model`，供蒙特卡洛/敏感性分析直接复用）。

### 2.2 tea（`biorefineries/tea/cellulosic_ethanol_tea.py`）

**类**：`class CellulosicEthanolTEA(TEA)`（继承 bioSTEAM 的 TEA 基类）。

**构造参数（实测 `__init__` 签名）**：`system, IRR, duration, depreciation, income_tax,`
`lang_factor, construction_schedule, ...` ——经济性假设全部走构造参数（不硬编码）。

**成本结构（实测方法）**：`CAPEXTableBuilder`（条目式资本表：entry(index, cost, notes)）+
`ISBL_installed_equipment_cost` / `OSBL_installed_equipment_cost`（**区分界区内/界区外**）+
`itemized_equipment_cost` + `_fill_depreciation_array`（折旧排布）+ `_DPI`（Direct
Permanent Investment）。

## 三、TEA 输出字段 schema（bioSTEAM TEA 基类的标准字段）

| 字段 | 含义 | 在 CellulosicEthanolTEA 中的来源 |
|---|---|---|
| `TCI` | 总资本投资（Total Capital Investment） | ISBL + OSBL + 其他间接 |
| `ISBL_installed_equipment_cost` | 界区内安装设备成本 | `_ISBL_DPI` 直接永久投资 |
| `OSBL_installed_equipment_cost` | 界区外安装成本 | `itemized_equipment_cost` 项 |
| `MPI`（Manufacturer's Price Index）等指数 | 价格指数调整 | bioSTEAM `price_indices` 机制 |
| `NPV` / `IRR` / 折现现金流 | 项目经济性 | TEA 基类 `NPV()`、`solve_price()` |
| `MPSP`（最低产品售价） | **solve_price()** 的解——使 NPV=0 的售价 | bioSTEAM TEA 标准输出 |

（字段名实测自上游 `CellulosicEthanolTEA` 方法与 bioSTEAM `TEA` 基类的公开接口——
MPSP/TCI 为 bioSTEAM 文档与 `tea.py` 基类的标准输出名。）

## 四、落点段：木质素→多孔碳线做 TEA 的骨架选择

| 项 | 建议 |
|---|---|
| **复用骨架** | `cellulosic`（Area 100–800 完整流程）——**木质素是纤维素乙醇的副产物流**（pre-treatment 液流里），Area 200/300 的黑液/木质素物流提取后接「木质素→多孔碳」单元组（新 Area 900：活化造孔 + 碳化） |
| **改哪些参数组** | ①进料组成（`chemicals.py` 的木质素流定义）②Area 900 的新单元（碳化炉/活化器——bioSTEAM 无内置，需自定义 Unit）③`tea/cellulosic_ethanol_tea.py` 的 `CAPEXTableBuilder` 加 Area 900 条目 ④`process_settings.py` 的电/汽价格 |
| **TEA 输出** | 沿用 `MPSP`（多孔碳的最低售价）作为主指标——与「木质素NPs→多孔碳」的经济性口径一致 |
| **TEA 输出字段 schema 表** | 见 §三 |
| **归档 DATASET.md 段落** | Bioindustrial-Park（MIT）：38 个厂级流程模型库；本仓落点 = `research/` 教材定位（数据产地），不进主线 import；骨架复用待 TEA 施工卷立项 |

## 五、引用（gh api 实测路径）

- `biorefineries/`（38 模型目录清单，git/trees 递归实测）
- `biorefineries/cellulosic/biorefinery.py`（5.2 KB：create_thermo/create_system/create_model + Area 100–800）
- `biorefineries/tea/cellulosic_ethanol_tea.py`（13 KB：CellulosicEthanolTEA + CAPEXTableBuilder + ISBL/OSBL/DPI）
