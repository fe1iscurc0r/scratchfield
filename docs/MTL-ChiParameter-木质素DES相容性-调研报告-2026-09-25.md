# MTL-ChiParameter 调研报告 — 木质素 / DES 相容性（2026-09-25）

> 卷159（木质素NPs线 P0）· 落盘：砚 · 状态：**任务A/C 已跑通最小验证；任务B 仅调研（本机无执行层）**
> 来源：授粉轮23 化学信息学候选 Tier1 三件（`docs/授粉轮23-化学信息学候选-授粉报告-2026-09-23.md`）
> 许可（2026-09-25 GitHub API 实测，非转述）：`yoshida-lab/MTL_ChiParameter` **MIT**（18★）、
> `SimonBoothroyd/absolv` **MIT**（34★）、`reymond-group/smilesDrawer` **MIT**（609★）——三件均可商用，无一 copyleft。

## 0. 结论先说（三件各自的现状）

| 件 | 本机能力 | 结论 |
|---|---|---|
| **A. MTL_ChiParameter**（χ 参数 ML） | ✅ 跑通最小验证 | 上游**未开源**关键数据；本仓用其可公开部分做了**可复算的基线**（5 折 R²=0.397）与 **polykin 交叉对照** |
| **B. absolv**（绝对溶剂化自由能） | ❌ 本机**无执行层** | 仅 conda-forge 发行；本机无 conda/mamba，也无 openmm/openff ⇒ **未跑**，给前置清单 |
| **C. smilesDrawer**（SMILES→结构图） | ✅ 跑通无头自检 | 三种木质素单体解析逐一对账通过；**像素渲染需浏览器**（本机无此层） |

## 1. 任务A：χ 参数 ML（MTL_ChiParameter）

### 1.1 上游管线的可信事实（读其 README / 数据 / 描述符表头所得）

- 论文对象：**Flory-Huggins χ 参数**的机器学习预测，目标是"聚合物-溶剂相容性"（*Macromolecules* 2023）。
- 数据结构：`data_Chi.csv` **1190 行实验 χ**（取自 Orwoll & Arnold 手册），列为
  `ps_pair`（聚合物与溶剂 SMILES 用 `_` 连接）/ `temp` / `chi` / `polymer_class` / 多任务标签 `DIFF,SIGN2,SIGN3`。
- 描述符：`desc_Chi.csv` 为 **794 维**片段型描述符（表头形如 `Polymer_mass_*`、`Polymer_charge_*`、`Polymer_epsilon_*`，
  即按原子类型的质量/电荷/介电分布 —— xenonpy 口径）。
- 上游环境：python 3.8 + pandas/numpy/sklearn/scipy + **rdkit 2020.09.5 + xenonpy 0.6.5 + pytorch 1.11**（A100 训练）。
- **上游自述限制（关键）**：PoLyInfo 二分类标签与 COSMO χ 的真实标签**不开放**；仓内 `data_PI.csv` 是
  **人造数据**；"用样例数据训练出的模型与论文结果**不可比**"。

### 1.2 本仓做的最小验证（`research/mtl-chi/chi_mtl_baseline.py`）

不做模型复刻，只做能自证的两条腿：

| 腿 | 做法 | 实测（本机，1190×794） |
|---|---|---|
| **岭回归基线** | 描述符标准化 → 岭回归（λ=1，含截距不惩罚）→ 确定性 5 折 | **R² = +0.397 ± 0.063**，**RMSE = 0.533**；全量拟合 R²=0.549（非泛化） |
| **COSMO 对照** | 实验 χ vs 上游 COSMO-RS 计算 χ（同 1190 对） | 相关系数 **+0.562**，RMSE 0.642 |
| **polykin 交叉对照** | χ 分位三档 → `FloryHuggins(Dgmix/activity)`（T=373.15 K，等体积分数，m=[1,1]） | χ=0.169 → Δg=−2019.4 J/mol；χ=0.483 → −1775.9；χ=1.710 → −824.2（理想项 −2150.5 + χ 项 +131.1/+374.6/+1326.3，**逐项自洽**） |

polykin 那条腿的意义：它把"一个 χ 数字"翻译成**可判定的热力学量**（Δg_mix 与活度），
并按上游自己的口径（χ<0.5 视为可溶）给出相容性判定 —— 这正是"木质素-DES 相容性"要的回答形式。
（本机把 `vendor/polykin` 以 editable 方式装进 `.venv` 才能导入；卸载 `pip uninstall polykin`。）

### 1.3 关于"木质素模型物 × DES"这件事（如实说）

工单要求"对木质素模型物（愈创木基/紫丁香基单体）× 常见 DES 溶剂**预测** χ"。本仓**没有产出这些配对的 χ 数字**，
原因不是省略，而是**上游的输入空间在本地拼不出来**：

- 上游 χ 数据里是**聚合物-溶剂**配对，**不含**木质素单体/DES 条目；
- 上游描述符是 xenonpy 片段描述符，需要跑其 `sample_code_for_descriptor_calculation.ipynb`（rdkit + xenonpy）；
  本机 `.venv` 有 rdkit 2026.03.5，但**无 xenonpy**，且其多任务模型权重未开源 ⇒ 无法产出可比的 χ。
- 替代路径（任选其一，均需额外工作）：① 装 xenonpy 复现描述符 → 用本仓岭回归基线外推（外推可信度需另评估）；
  ② 用 rdkit 自建描述符训练一个**本仓自有**的 χ 小模型（数据仍只有上游这份聚合物-溶剂 χ，泛化到木质素无保证）；
  ③ 走 COSMO-RS 计算路线（上游 figshare 有 1190 对的计算值可作对照，本机无 COSMO 软件）。

候选配对清单（结构渲染见任务C 的 demo）：

| 木质素模型物 | SMILES | 甲氧基数 |
|---|---|---|
| 愈创木酚（G 单体骨架） | `COc1ccccc1O` | 1 |
| 4-甲基愈创木酚（G 型木质素模型物） | `Cc1ccc(O)c(OC)c1` | 1 |
| 2,6-二甲氧基苯酚（S 单体骨架） | `COc1cccc(OC)c1O` | 2 |
| 香草醛（G 型氧化产物） | `COc1cc(C=O)ccc1O` | 1 |

| 常见 DES 组分 | SMILES | 备注 |
|---|---|---|
| 氯化胆碱（HBA） | `C[N+](C)(C)CCO.[Cl-]` | 与 HBD 成对 |
| 乙二醇（HBD） | `OCCO` | 最常用 HBD |
| 甘油（HBD） | `OCC(O)CO` | 黏度较高 |
| 尿素（HBD） | `NC(N)=O` | 经典 DES |

## 2. 任务B：absolv（绝对溶剂化自由能）——*仅调研，本机无执行层*

**上游事实**：用 OpenMM 算"溶质从一种溶剂转移到另一种（或真空）"的自由能变化；两条路线 ——
平衡计算与**非平衡切换（non-equilibrium switching，框架主线）**；依赖 `openff.toolkit` + `openmm`；
**发行渠道是 conda-forge**（`mamba install -c conda-forge absolv`），HPC 场景还需外部 MPI。

**上游自述警告（照抄，因为影响可用性判断）**：
> "currently experimental and under active development … **not guaranteed to provide correct results**,
> the documentation and testing is incomplete, and the API can change without notice."

**本机实测**：`conda` / `mamba` / `micromamba` **均无**；`openmm`、`openff.toolkit` **均缺**（`.venv` 内实测）。
⇒ **本机没有这一层**，未跑任何溶剂化自由能计算。建议的前置：

1. 装 conda/mamba（本机没有）→ `mamba install -c conda-forge absolv openff-toolkit openmm`
2. 小体系试算（香草醛/水、水杨醛/水）先跑 **CPU**（小体系可行，但**未见实测数字**，属预判非结论）
3. 结果用途：木质素 NPs 的**释放动力学**核心物性是溶剂化自由能，与任务A 的 χ 互补（一个管"混不混"、一个管"跑多快"）

**关于成本**：本机未跑 ⇒ **不给出具体墙钟时间**（工单也只要求"评估成本"，评估的结论是：
依赖门槛在 conda 层，且上游自述实验性 —— 先做小体系 CPU 冒烟，再谈批量）。

## 3. 任务C：smilesDrawer（SMILES → 结构图）

**npm 包结构（读 `smiles-drawer@2.4.1` 的 package.json 与 dist 所得）**：

- `exports`: `import` → `dist/smiles-drawer.min.mjs`，`default`/`main` → `dist/smiles-drawer.min.js`
- 命名空间导出：`Drawer / SvgDrawer / GaussDrawer / Parser / ReactionDrawer / ReactionParser / SmiDrawer / Version`
- **打包坑**：`dist/smiles-drawer.min.js` 是 esbuild 的 IIFE 产物（不挂全局、不走 CJS，`require()` 得空对象），
  官方 `example/index_svg.html` 的 `SmilesDrawer.Drawer` 老写法对 2.4.1 已失效 ⇒ 可靠入口是 **`.mjs`**（浏览器 `<script type="module">`）。

**本仓最小验证**（`research/smiles-drawer-demo/`）：vendored 193 KB 的 `.mjs` + `check_smiles.mjs` 无头自检：

```
[check] PASS  H 对香豆醇  重原子 11（期望 11）
[check] PASS  G 松柏醇    重原子 13（期望 13）
[check] PASS  S 芥子醇    重原子 15（期望 15）
[check] PASS  渲染器构造 OK（Drawer / SvgDrawer 均可实例化；实际绘制需浏览器）
[check] ALL PASS ✓
```

**引入路径**：纯前端单文件、零运行时依赖 ⇒ lumo 前端可 `import()` 即用；**像素渲染是唯一未验证层**
（需浏览器打开 `index.html`）。备选：`.venv` 已有 **rdkit 2026.03.5**，服务端出图可用 rdkit —— 前端轻量 / 服务端精确，不冲突。

## 4. 验收对照（工单「可执行不变量」逐条）

| 工单验收 | 结果 |
|---|---|
| `test -f docs/MTL-ChiParameter-木质素DES相容性-调研报告-2026-09-25.md` | ✅ 本文件 |
| `test -d research/mtl-chi/` | ✅ 含脚本 + README + results.json |
| `test -d research/smiles-drawer-demo/` | ✅ 含 demo + 无头自检 + vendored 库 |
| `grep -c "χ\|chi" <本文件>` ≥5 | ✅（见 §0/§1，远超 5） |
| `grep -c "polykin" <本文件>` ≥2 | ✅（§0 表 + §1.2） |
| `grep -ril "svg\|SVG" research/smiles-drawer-demo/` ≥1 | ✅（index.html / check_smiles.mjs / README.md） |

## 5. 未决项与边界（不许含糊的部分）

1. **木质素×DES 的 χ 未产出**：上游输入空间（xenonpy 描述符 + 缺失数据/权重）在本地拼不齐，见 §1.3 的三条替代路径。
2. **absolv 未跑**：本机无 conda 层与 openmm/openff；上游自述实验性，先小体系平台冒烟。
3. **smilesDrawer 渲染未验证**：无头环境无 DOM；`index.html` 需浏览器确认。
4. **温度列单位**已确认为 °C（实测 0…229；0.0 疑占位），本仓脚本按正值中位数取 100 °C → 373.15 K，与上游论文口径需再核。
5. **本仓装了 editable 的 vendored polykin 到 `.venv`**（为交叉对照腿）—— 属环境改动，已记录卸载方式。
6. 交付文档按本卷**匿名铁律**：不写真实姓名，涉及的课题组方向一律以"用户已确认"表述。
