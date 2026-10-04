# mofdscribe 描述符 schema 勘察 · 2026-10-01（卷168-B）

> 上游：`lamalab-org/mofdscribe`（MIT，⭐52）——纯文档勘察（gh api 静态分析，**未整仓 clone**）。
> ⚠️ **导入受限声明**：本机实测 `mofdscribe.featurizers` 无法导入（`setuptools≥81` 移除
> `pkg_resources` + 当前 pymatgen 移除 `BrunnerNN_relative`——已提上游 issue
> [#462](https://github.com/lamalab-org/mofdscribe/issues/462)）。因此本报告的 schema
> 基于**源码静态分析**（git trees + 关键文件实测），运行时行为待上游兼容后复核。

---

## 一、schema 总览（行=材料，列=描述符族）

实测源码树：**featurizers 94 个模块**、**datasets 24 个模块**（gh api 实测文件清单）。

### featurizers 族（从模块结构归纳，静态分析）

| 族 | 模块（`src/mofdscribe/featurizers/`） | 描述内容 |
|---|---|---|
| **BU（building-unit）族** | `bu/bu_featurizer.py`、`bu/compositionstats_featurizer.py`、`bu/distance_hist_featurizer.py`、`bu/distance_stats_featurizer.py`、`bu/lsop_featurizer.py`、`bu/nconf20_featurizer.py`、`bu/shape_featurizer.py`、`bu/smarts_matches.py`、`bu/rdkitadaptor.py` | 在**构建单元（BB）层**算描述符：组分统计、距离直方图/统计、LSOP（局域结构序参量）、NCONF20（构象）、形状、SMARTS 匹配（经 rdkit） |
| 结构几何族 | （`str/`、`grid/` 等子目录，94 模块未全列） | 孔径分布/表面积类几何描述符（与 porespy 输出可对齐的部分） |
| 基类 | `base.py` | 统一的 featurizer 基类（`featurize()` 协议——matminer 风格） |

### 内置数据集接入（`src/mofdscribe/datasets/`）

实测模块名（节选）：`arabg_dataset.py`、`arcmof_dataset.py` 等——**数据集以模块化类提供**
（按名字加载基准集），而非打包 CSV。

### 版本 pin（实测）

- `pyproject/setup.py` 的依赖：`pymatgen`（**未 pin 上限**——导致 §三的不兼容）、`matminer`、`rdkit`、`ase`、`loguru`、`pystow`
- 上游 **0.0.8 落后于 pymatgen 新版**（`BrunnerNN_relative` 已从 `pymatgen.analysis.local_env` 移除）——**已提上游 issue #462**

## 二、落点映射（描述符族 ↔ 木质素NPs→多孔碳的表征手段）

| mofdscribe 描述符族 | 木质素 NPs→多孔碳 线的对应表征 | 复用方式 |
|---|---|---|
| BU 族（组分统计/距离统计） | 木质素衍生物的**官能团/元素组成**表征 | SMILES/组成输入即可复用（经 rdkitadaptor） |
| 形状/几何族 | SEM/CT 图像（porespy）的**孔几何** | porespy 出孔网 → 转结构图 → 几何族对齐（需适配层） |
| LSOP/NCONF20 | 碳材料**局域结构序**（石墨化程度） | 概念对齐，需构造碳模型输入 |
| datasets（arabg/arcmof 基准） | 基准对照系 | MOF 基准 ≠ 多孔碳——只作方法论参考 |

**结论**：可直接复用的是 **BU 族 + rdkitadaptor**（分子层描述符）；几何族需 porespy→
结构图的适配（本仓已有 porespy 管线，输出孔网图即可接）。

## 三、引用（真实文件路径）

- `src/mofdscribe/featurizers/base.py`（featurizer 基类协议）
- `src/mofdscribe/featurizers/bu/*.py`（BU 族 14 模块）
- `src/mofdscribe/datasets/arabg_dataset.py`、`arcmof_dataset.py`
- 上游 issue：[#462](https://github.com/lamalab-org/mofdscribe/issues/462)
  （pkg_resources / pymatgen API 两障碍的完整复现链）
