# BO 自驾驶材料实验设计 · 木质素 NPs 合成寻优 · HOTEL-01

> 工单：H-01（BO 自驾驶材料实验设计，只读勘察 + 设计，不写码）
> 线：HOTEL（BO 自驾驶材料实验 · 木质素合成寻优）｜分支：trae/agent-hotel
> 上游：ALPHA 线 `docs/xtalyst-wetdry-木质素NPs-设计.md`（wet-dry loop 闭环设计）
> 定位：把 Xtalyst 的 **"推荐→重扫→再分析"反馈环** 升级为 **"主动学习寻优"**——代理模型预测合成条件→性能映射，采集函数选下一个实验点，失败实验也进训练。
> 完成：2026-08-28

---

## 〇、一句话结论

贝叶斯优化（Bayesian Optimization, BO）把 Xtalyst wet-dry loop 的**规则表推荐器**替换为**数据驱动的代理模型 + 采集函数**：每次只用"最值得做的下一个实验"替代"经验试错"与"全网格粗扫"，并首次把**失败实验**与**混合变量**显式纳入模型。工具链结论：**本项目环境未装 scikit-optimize/optuna/GPyOpt（已验证），故一期用 numpy/sklearn 轻量自实现（随机森林代理 + EI/UCB 采集函数）**，这也是 H-02 的落地路径；不引入重依赖。

---

## 一、输入与现状勘察

### 1.1 三条输入

| # | 输入 | 状态 |
|---|---|---|
| 1 | BO 论文综述授粉点（8-28 轮第 3 条：Agentic Autoresearch + 自驾驶材料实验室 BO） | 5 个映射见 §三，逐条落地方案见 §四 |
| 2 | `docs/xtalyst-wetdry-木质素NPs-设计.md`（ALPHA 交付） | 已读；其 §六 参数表/校正规则是本文参数空间的直接来源 |
| 3 | `mcpserver/material_science/` 现状（`biopred.py` / `materialscience_agent.py`） | 已读；接口见 §1.2 |

### 1.2 material_science 现状（读接口，不破坏）

| 文件 | 现有能力 | 与 BO 的关系 |
|---|---|---|
| `biopred.py` | `predict(desc, db_path)` 单点预测 + 置信区间；`suggest(db_path, target)` 网格枚举 + 探索度打分 | `suggest` 是"网格穷举 + 距最近邻距离"的朴素主动学习，**BO 是其工程化升级**：从"枚举网格挑最远点"→"代理模型 + 采集函数选下一点" |
| `materialscience_agent.py` | `MaterialScienceAgent` 工具注册 + `handle_handoff` 调度 | BO 旁路不注入 agent 主流程，独立目录 `bo_optim/`，避免 `git diff` 触及主流程 |
| `duckdb_workbench/` `graphrag/` `writing_pipeline/` `academic_bridge/` | 数据/图/写作/文献子模块 | 与 BO 无直接耦合，仅共享 numpy/sklearn 依赖 |

> 勘察结论：`biopred.suggest` 已经埋下"主动学习"的种子，但只做**单目标 + 全网格 + 探索度**，未做**代理模型不确定性驱动的采集函数**、**失败实验纳入**、**混合变量**、**多目标**。BO 旁路补齐这四块，且不改动 biopred 主流程。

---

## 二、BO 流水线图

### 2.1 概念流水线（验收要求的五步链）

```
参数空间 (parameter space)             代理模型 (surrogate model)           采集函数 (acquisition)
┌─────────────────────┐            ┌──────────────────────────┐          ┌──────────────────────────┐
│ 连续: T / t / C / 配比 │  ──拟合──▶ │ GP 或 随机森林             │ ──输出──▶ │ EI / UCB / 随机          │
│ 离散: 溶剂/来源/pH    │            │ f: x → (μ, σ) 预测+不确定性 │          │ 在候选集上选最大值        │
└─────────────────────┘            └──────────────────────────┘          └────────────┬─────────────┘
        ▲                                                                              │ 下一点 x*
        │                                                                              ▼
        │ 实测回填 (record / update)                           ┌──────────────────────────────┐
        └──────────────────────────────────────────────────────│ 实测 (synthesize + measure)    │
                                                               │ 成功→指标；失败→失败标记纳入训练 │
                                                               └──────────────────────────────┘
```

### 2.2 闭环伪代码（对齐 H-02 模块边界）

```python
# 概念闭环（对应 bo_optim 包的 loop.py / surrogate.py / acquisition.py）
space   = lignin_hydrothermal_space()          # params.py：参数空间 + 约束
sur     = make_surrogate("rf")                 # surrogate.py：代理模型 fit/predict/uncertainty
acq     = expected_improvement                 # acquisition.py：采集函数
loop    = BOLoop(space, sur, acq)              # loop.py：闭环状态机

loop.init(n_init=4)                            # 初始点（粗扫：正交/拉丁超立方采样）
while not loop.converged():
    x_next = loop.recommend()                  # 采集函数选下一点
    batch  = loop.recommend_batch(k)           # 可导出为下一批配方表 CSV
    y      = synthesize_and_measure(x_next)    # 湿环节：真实实验，不可模拟
    loop.record(x_next, y)                     # 实测回填（含失败实验 y=None + failed=True）
    loop.update()                              # 用全量历史（含失败）重拟合代理模型
```

> `synthesize_and_measure` 是真实实验步骤；BO 只负责"选下一点"，不替代湿环节。所有实测值缺省标 `None = 待真机`。

---

## 三、BO 综述 5 映射（授粉点提炼）

| # | 授粉点（BO 综述） | 原义 | 映射到木质素 NPs 水热合成 |
|---|---|---|---|
| 1 | **失败实验纳入训练** | 失败/负结果是信息，不是垃圾——它告诉代理模型"哪里不该去" | 合成失败 / 门 FAIL 的批次也进训练集，给惩罚目标值，采集函数主动避开 |
| 2 | **混合变量（连续 + 离散）** | 真实实验空间混合连续（温度/时间）与离散（溶剂/来源） | 参数空间 `continuous` + `categorical` 分区，one-hot 编码，采集时枚举候选（不用连续梯度） |
| 3 | **多目标（收率 + 粒径 + 凝胶强度）** | 单目标寻优不满足材料多指标权衡 | 一期标量化（加权分数 + 方向），二期 Pareto / EHVI；凝胶强度为下游水凝胶/共熔凝胶指标 |
| 4 | **成本-保真度（廉价粗测先行）** | 多保真度：廉价粗测先大面积筛，昂贵精测只对候选 | 粗测（收率 + DLS PDI，快/零外送）先行；TEM/PXRD 精扫只在可靠性门 FAIL 时补测 |
| 5 | **历史数据迁移（旧实验预热代理模型）** | 用历史/旧课题数据 warm-start，减少冷启动 | 历史 ELN / 碳化记录（biopred 的 carbonization.db）并入初始训练集预热代理模型 |

---

## 四、5 映射落地方案（逐条）

### 映射 1 · 失败实验纳入训练

- **方案**：`loop.record(x, y, failed=False)` 支持失败标记。失败点的目标值置为**域内最差值 + 惩罚**，并保留 `failed=True` 元数据；`loop.update()` 时失败点与其他点**一并进训练集**，让代理模型学会"该区域低分"。
- **采集层面**：`acquisition.py` 提供 `penalize_failed=True` 开关——在采集函数上叠加"与失败点距离成反比的惩罚"，进一步压低失败邻域。
- **落地代码**（H-02）：`loop.record` / `loop.update` + `acquisition` 的失败惩罚项。
- **诚实标注**：失败点"最差值 + 惩罚"的**惩罚幅度是设计假设**，需一期真机标定；`None=待真机`。

### 映射 2 · 混合变量（连续 + 离散）

- **方案**：`params.py` 用 `ParameterSpace` 同时承载：
  - `continuous: {name: (low, high)}`（温度、时间、浓度、配比）
  - `categorical: {name: [choices]}`（溶剂体系、pH 档、木质素来源）
- **编码**：`encode(x) → float 向量`（连续标准化 + 离散 one-hot）；`decode(vec) → 配方 dict`。
- **采集**：`recommend()` 在**随机候选集（离散全枚举 × 连续采样）**上打分取最大，天然支持混合变量，不依赖梯度。
- **落地代码**：`params.py`（含内置 `lignin_hydrothermal_space()` 示例）。

### 映射 3 · 多目标

- **方案（一期）**：标量化——`objective = Σ w_i · sign_i · normalize_i(metric_i)`，每个指标给方向（最大化收率、最小化 PDI、粒径落在目标区间、最大化凝胶强度）与权重。
- **方案（二期）**：Pareto 前沿 + EHVI（期望超体积改善），保留非支配解集。
- **凝胶强度**：属于下游"木质素 NPs → 水凝胶/共熔凝胶"应用指标，**不在 xtalyst 原始三指标（收率/粒径/PDI）内**，落地前需先定测量方法（流变/穿刺/压缩），标"待真机"。
- **落地代码**：`loop.py` 的标量化 objective（方向 + 权重可配）；二期 EHVI 留扩展点。

### 映射 4 · 成本-保真度

- **方案**：两档保真度。
  - **低保真（粗测，每轮必做）**：质量收率（烘干称重）+ DLS PDI（有粒度仪即可），零外送、快。
  - **高保真（精测，门 FAIL 才补）**：TEM（外送瓶颈）、PXRD 精扫。
- **与 xtalyst 对齐**：这正是 xtalyst 的 coarse → fine 两扫结构——可靠性门不过才触发精测，避免对失败批次做全套表征。
- **落地代码**：`loop.record` 的 `fidelity` 字段（low/high），`recommend` 优先在低保真上推进；高保真补测作为门 FAIL 后动作。

### 映射 5 · 历史数据迁移

- **方案（一期）**：warm-start——把历史实验记录（ELN 导出 / `biopred.py` 的 `carbonization.db` / `experiment_records_template.csv`）直接并入初始训练集，让代理模型第一轮就有先验，而非从 n_init 个随机点冷启动。
- **方案（二期）**：跨课题迁移学习（多任务 GP / 元学习），旧课题（碳化）→ 新课题（水热 NPs）的相似度加权先验。
- **落地代码**：`loop.init(warm_start=records)` 接受历史记录预热；CLI `record --from-csv` 批量导入历史。

---

## 五、参数空间表（木质素 NPs 水热合成）

> 范围与阈值均为**领域常识级设计假设**（继承 ALPHA 线 §六），非实测；落地前逐项"待真机/实测确认"。

### 5.1 可调参数（干侧设计空间）

| 参数 | 符号 | 类型 | 设计范围（假设，待确认） | 说明 |
|---|---|---|---|---|
| 水热温度 | T | 连续 | 140–220 °C | 影响成核/生长与结晶度 |
| 保温时间 | t | 连续 | 2–24 h | 影响粒径与收率 |
| 木质素浓度 | C | 连续 | 1–20 mg/mL | 影响粒径与团聚 |
| 前驱体/交联剂配比 | R | 连续 | 1–10（质量比，假设） | 影响凝胶强度/交联度 |
| 溶剂体系 | S | 离散 | {纯水, 乙醇-水} | 影响分散与形貌 |
| pH 档 | pH | 离散 | {酸性, 中性, 碱性} | 影响溶解/沉淀路径 |
| 木质素来源 | L | 离散 | {碱木质素, 酶解木质素, 其他} | 影响分子量与官能团 |

### 5.2 目标指标（湿侧）

| 指标 | 手段 | 方向（假设，待确认） | 保真度 |
|---|---|---|---|
| 质量收率 | 烘干称重 | 最大化（达课题下限） | 低（每轮必测） |
| 粒径 Z-average | DLS | 落在目标区间（如 100–300 nm） | 低（每轮必测） |
| 多分散指数 PDI | DLS | 最小化（≤ 0.3 均匀） | 低（每轮必测） |
| 凝胶强度 | 流变/穿刺（待定方法） | 最大化 | 高（门 FAIL 补测） |
| 结晶度/峰位 | PXRD | 峰可辨 + 无异常漂移 | 高（门 FAIL 补测） |

### 5.3 约束

| 约束 | 类型 | 值（假设） | 来源 |
|---|---|---|---|
| 设备温度上限 | 硬约束 | T ≤ 220 °C（水热釜上限） | 设备限制 |
| 原料批次 | 离散约束 | 单批同源木质素（来源 L 固定一次循环） | 原料批次 |
| 单轮实验节拍 | 软约束 | TEM/PXRD 外送瓶颈，非每轮必测 | 成本-保真度（映射 4） |

---

## 六、工具链选型

| 工具 | 许可 | 核心依赖 | 维护/成熟度 | 本项目现状 | 结论 |
|---|---|---|---|---|---|
| **scikit-optimize (skopt)** | BSD-3-Clause | scikit-learn, numpy, scipy | 维护放缓，与新 sklearn 版本有兼容摩擦 | **未装**（`import skopt` 失败） | 功能最贴合（EI/GP/RF 内置），但版本兼容风险高 |
| **Optuna** | MIT | numpy, scipy（可无 GPU） | 活跃维护，生态好 | **未装**（`import optuna` 失败） | 最活跃，但引入一套 study/trial 框架，对本旁路偏重 |
| **GPyOpt** | BSD（BSD-3） | GPy, numpy, scipy | 维护停滞 | **未装**（`import GPyOpt` 失败） | 依赖 GPy 较重，不选 |
| **numpy + scikit-learn 自实现** | 本项目 | numpy（必装✓）, scikit-learn（已装✓） | —— | **已装**（numpy 2.4.6 / sklearn 1.9.0 / pandas 2.3.3） | **选定**：随机森林代理（fit/predict/uncertainty）+ EI/UCB 采集函数，零新增依赖 |

**选型结论**：H-01 判定**外部 BO 工具链过重且未安装**（skopt 兼容风险、GPyOpt 依赖重、optuna 框架重），且工作订单明确"若工具链太重，用轻量实现（numpy 手写 GP 或随机森林代理）"。因此 **H-02 采用 numpy/sklearn 轻量自实现**：

- **代理模型**：`surrogate.py` 提供 `RandomForestSurrogate`（sklearn，点预测 + 树间标准差作不确定性）与 `GaussianProcessSurrogate`（numpy 手写 RBF GP，无 sklearn 依赖时的降级）；`make_surrogate("rf"|"gp")` 工厂选择。
- **采集函数**：`acquisition.py` 提供 `expected_improvement` / `upper_confidence_bound` / `random`，均纯 numpy。
- **运行依赖标注**：numpy（必需）、scikit-learn（RF 代理，GP 降级路径可无）、pandas（CSV 导出，可选）。H-02 硬约束满足"纯 Python + 轻依赖"。

---

## 七、验收 grep 项

```bash
# H-01 设计自检
grep -q "参数空间"          docs/bo-自驾驶材料实验-设计.md
grep -q "代理模型"          docs/bo-自驾驶材料实验-设计.md
grep -q "采集函数"          docs/bo-自驾驶材料实验-设计.md
grep -q "失败实验纳入训练"   docs/bo-自驾驶材料实验-设计.md
grep -q "混合变量"          docs/bo-自驾驶材料实验-设计.md
grep -q "多目标"            docs/bo-自驾驶材料实验-设计.md
grep -q "成本-保真度\|廉价粗测" docs/bo-自驾驶材料实验-设计.md
grep -q "历史数据迁移\|warm-start" docs/bo-自驾驶材料实验-设计.md
grep -q "scikit-optimize\|optuna\|GPyOpt" docs/bo-自驾驶材料实验-设计.md
grep -q "待真机\|待确认\|设计假设"   docs/bo-自驾驶材料实验-设计.md
```

---

## 八、诚实标注（不臆造清单）

1. §五 所有参数范围/阈值/方向均为设计假设，未实测，落地前标定。
2. 凝胶强度测量方法（流变/穿刺/压缩）尚未确定，标"待真机"。
3. 失败点惩罚幅度、采集函数超参（κ/ξ）、n_init 初始点数均为设计值。
4. BO 论文收益（轮次减少、采样效率）**不能直接外推**到木质素 NPs 合成收率，仅作机制依据。
5. 历史数据迁移的跨课题相似度（碳化 → 水热 NPs）一期按"直接并入训练集"处理，二期再做相似度加权，不做无据假设。

---

*执行：智能体 HOTEL · 2026-08-28 · H-01 只读勘察 + 设计（不写码）*
