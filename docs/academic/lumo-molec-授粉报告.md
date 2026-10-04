# Lumo 分子设计/实验设计库授粉报告（工单 E-02）

> 来源：experimental-design/bofire（402★，BSD-3）、isayev/ReLeaSE（372★，MIT）、DSPsleeporg/smiles-transformer（358★，MIT）
> 审查：实验田维护者（Hermes）｜日期：2026-08-23
> 定位：面向生物质能源与材料方向，评估 3 个实验设计/分子生成库 → 是否进 Lumo MCP 封装
> 仓库核实说明：任务给的 pemami4911/ReLeaSE 与 PSZlen/smiles-transformer 均已 404，经 GitHub API 核实正主为 isayev/ReLeaSE 与 DSPsleeporg/smiles-transformer（描述与论文一一对应）。

---

## 〇、结论表（先给结论）

| 库 | 定位 | 许可 | 结论 | 理由 |
|---|---|---|---|---|
| **bofire**（experimental-design/bofire） | 实验设计 + （多目标）贝叶斯优化框架，化工/制药工业界在用 | BSD-3-Clause | **进MCP封装** | 活跃维护（v0.5.0，2026-08 仍在发版）；自带问题/策略/代理模型序列化 → 天然契合 MCP JSON 契约；连续/离散/类别变量 + 约束 + 单/多目标 BO 完整覆盖生物质实验变量（温度/配比/时间）；PyTorch/BoTorch 依赖按"依赖缺失降级"模式处理即可 |
| **ReLeaSE**（isayev/ReLeaSE） | 深度强化学习 de novo 分子生成（stackRNN 生成器 + 属性预测器做 reward） | MIT | **只参考** | 代码价值≈0：Jupyter demo 形态、无 pip 包、依赖锁死 2018 年（PyTorch 0.4.1/TF 1.8/CUDA 9/Python 3.6）、2021 年停更；只授粉其「生成器-预测器-RL 两阶段」架构思想（详见 §三迁移成本专项） |
| **smiles-transformer**（DSPsleeporg/smiles-transformer） | 预训练 SMILES autoencoder → 分子指纹嵌入，面向低数据药物发现（表示学习，**非生成**） | MIT | **只参考** | 没有分子生成管线（`sample.py` 只是 SMILES 枚举 demo）；价值在预训练嵌入 → 小样本性质预测，可平移给生物质平台分子，但需领域微调 + 权重外部下载；若实验田维护者后续要"小样本分子性质预测"能力再评估封装 |

---

## 一、bofire —— 进 MCP 封装

### 1.1 定位与许可

bofire（**B**ayesian **O**ptimization **F**ramework **I**ntended for **R**eal **E**xperiments）是实验设计 + 黑盒优化框架，由化工/制药工业界（BASF、Bayer、Evonik 等）与学术伙伴共同开发，JMLR OSS 发表论文。BSD-3-Clause 许可（Copyright 2022 evonik-dev），宽松可商用可封装；仓库活跃（latest release v0.5.0，2026-08-11），PyPI 直接 `pip install bofire[optimization]`。

### 1.2 核心 API（仅列接口名，不复制代码）

- **搜索空间**：`bofire.data_models.features.api` → `ContinuousInput`（含 bounds）/ `ContinuousOutput` / `CategoricalInput` / `DiscreteInput`（枚举取值）/ `TaskInput`（批次效应）/ 派生特征（`SumFeature`、`MeanFeature`、`InterpolateFeature` 等）；另有 `Descriptors` 与 tanimoto 核代理（`tanimoto_gp_surrogate`）支撑分子变量。
- **目标**：`bofire.data_models.objectives.api` → `MinimizeObjective` / `MaximizeObjective` / `CloseToTargetObjective`，目标与输出解耦。
- **域与约束**：`bofire.data_models.domain.api` → `Domain(inputs, outputs, constraints)`；约束支持线性约束、NChooseK 约束、非线性约束、黑箱输出约束。
- **策略**：`bofire.strategies.api` → `SoboStrategy`（单目标 BO）、`MoboStrategy`/`QparegoStrategy`（多目标）、`DoEStrategy`/`FractionalFactorialStrategy`（初始实验设计）、`RandomStrategy`、`ShortestPathStrategy`、`StepwiseStrategy`、`LLMStrategy`（LLM 提候选，冷启动用）。
- **代理模型**：`bofire.surrogates` → `SingleTaskGPSurrogate`（BoTorch 底座）、multi-task GP、`RandomForestSurrogate`、MLP、fully-Bayesian、Tanimoto GP 等。
- **闭环原语**：`domain.inputs.sample(n)` 随机采样候选 → `strategy.ask(candidate_count=k)` 提候选 → `strategy.tell(experiments)` 吃实验结果更新代理 → 循环。
- **序列化**：data models 与 functional 分离，Domain/Strategy/代理模型可序列化 → 官方定位就是"无缝接入 RESTful API"，MCP 封装零摩擦。

### 1.3 与实验田维护者实验设计流程的结合（生物质材料实验）

实验田维护者的实验是典型的"多变量-少轮次-贵表征"场景（热解/水热碳化/催化转化，一次实验成本高、可做轮次少），正是贝叶斯优化的目标场景。映射方式：

1. **变量声明**：温度（℃）、时间（min）→ `ContinuousInput(bounds=[下限, 上限])`；原料:溶剂或催化剂配比 → `ContinuousInput` 或 `DiscreteInput`（枚举常用配比），配比类变量加线性约束（如组分和=100%）；原料种类/催化剂类型 → `CategoricalInput(categories=[...])`；多批实验 → `TaskInput` 吸收批次漂移。
2. **目标定义**：单目标（产物得率最大化）用 `SoboStrategy`；多目标（得率 vs 高位热值 HHV vs 单位能耗，或得率 vs 灰分）用 `MoboStrategy`/`QparegoStrategy` + 多个 `ContinuousOutput`；硬指标（如灰分 < 阈值）用输出约束。
3. **闭环流程**：第 0 轮用 `domain.inputs.sample()` 或 `DoEStrategy` 生成满足约束的初始实验矩阵（比人工正交表灵活，天然不产生越界组合）→ 实验田维护者做实验 → 结果回填 `experiments` → `tell` 更新 GP → `ask` 给出下一轮候选参数表 → 循环至收敛。
4. **与 Lumo 的接法**：MCP 工具面建议两个 command——`bofire_suggest`（输入：变量声明 JSON + 已做实验表 → 输出：下一批候选参数表 + 预测区间）与 `bofire_update`（吃一轮实验结果，返回代理更新状态）；Domain/Strategy 以 JSON 持久化到实验记录库（呼应 ChemGraph 授粉的 SQLite 记录层），实验历史即训练数据，天然形成"设计→实验→记录→再设计"闭环。
5. **冷启动增强**：`LLMStrategy` 可让 LLM 依据文献背景（如某温度区间/催化剂先验）提首轮候选，适合实验田维护者有文献先验但缺实验数据的起步阶段。
6. **依赖降级**：bofire 依赖 PyTorch/BoTorch（较重），按 MODEL_INTERFACE 既有模式处理——封装 `bofire_check` 工具 + 缺依赖抛 `AcademicDependencyError`（含 `pip install bofire[optimization]` 提示），只标注不否决。

---

## 二、ReLeaSE —— 只参考

### 2.1 定位与许可

ReLeaSE（Reinforcement Learning for Structural Evolution）是 Sci. Adv. 2018 论文《Deep Reinforcement Learning for de-novo Drug Design》的官方 PyTorch 实现：stacked RNN（生成器）先在大规模 SMILES 语料上预训练学"分子语法"，再用策略梯度（REINFORCE 类）以属性预测器（RNN 或随机森林）打分为 reward 做 RL 微调，生成满足性质约束的新分子。MIT 许可；372★；**2021-12 起停更**（最后 push 2021-12-08）。

### 2.2 Jupyter notebook 形态对封装的影响（迁移成本专项）

这是本库授粉决策的决定性因素，单独展开：

- **仓库形态**：顶层就是 3 个演示 notebook（`JAK2_min_max_demo.ipynb`、`LogP_optimization_demo.ipynb`、`RecurrentQSAR-example-logp.ipynb`）+ 源码目录 `release/`（`stackRNN.py`、`predictor.py`、`reinforcement.py`、`rnn_predictor.py`、`data.py`、`smiles_enumerator.py`、`utils.py`）+ 预训练权重（`checkpoints/generator/`、`checkpoints/logP/`）+ 语料（`data/chembl_22_clean_1576904_sorted_std_final.smi`，157 万条）。
- **无安装路径**：仓库**没有 setup.py/pyproject.toml**，`release/` 只能靠 import 或整段搬运；notebook 是入口，而 notebook 把数据加载→预训练→RL→评估混在一个 cell 流里，**没有函数级接口**。对比 MODEL_INTERFACE 中 tespy 的"pip 安装后依赖缺失降级"模式，ReLeaSE 连"可安装"这步都不满足，MCP 封装无从挂载。
- **依赖锁死 2018**：README 要求 Python 3.6 + PyTorch 0.4.1 + TensorFlow 1.8.0 + CUDA 9.0 + RDKit + Mordred（conda 环境安装）。现代环境（Python 3.10+/PyTorch 2.x）直接跑不通——RNN 相关 API 早已大改，Mordred 也基本停维护；实际迁移等于**用现代 PyTorch 重写 stackRNN + policy gradient + predictor 三个模块**。
- **迁移成本量化**：重写 ≈ 1–2 人周（三个模块 + 数据管道），且 RL 训练稳定性需要重新调参验证；全仓测试只有一个 `tests/stackRNN_tests.py`，无回归保障。投入产出比差。
- **结论**：**不封装、不迁移**。授粉价值 = 架构思想本身：「生成器预训练（学语法）→ 属性预测器做 reward → RL 微调」的两阶段范式，以及"预测器可换成随机森林等轻量模型"的降本设计。若未来真需要 RL 分子生成，应直接采用现代实现（如基于 RDKit + 现代 PyTorch 的分子 RL 框架），而非迁移 ReLeaSE。

---

## 三、smiles-transformer —— 只参考

### 3.1 定位与许可

SMILES Transformer（arXiv:1911.04738，Honda/Shi/Ueda）是**预训练分子指纹提取器**：在 ChEMBL24 的 170 万条 SMILES（配合 SMILES 枚举做数据增强）上以 autoencoding 任务预训练 transformer，之后把任意分子 SMILES 编码成固定长度稠密向量作为"预训练分子指纹"，用于下游任务（论文主打低数据药物发现场景）。MIT 许可；358★；结构与入口：`smiles_transformer/` 包（`build_corpus.py`、`build_vocab.py`、`enumerator.py`、`pretrain_trfm.py`、`pretrain_rnn.py`、`smi2csv.py`、`sample.py`）+ `experiments/`（`prepare_data.ipynb`、`evaluate.ipynb`、ablation_1..5.ipynb）。

### 3.2 能否用于生物质衍生分子设计（Q5 答复）

- **它没有分子生成管线**：`pretrain_trfm.py` 训练的是 autoencoder，产出的是编码器嵌入；`sample.py` 经核实只是 SMILES 枚举（随机化）演示脚本，**不是模型采样生成**。所以"生成全新生物质衍生分子"这一步它不提供，与任务描述中的"生成管线"有出入——这是本库"只参考"而非"进封装"的核心原因。
- **但表示学习路线可平移**：把生物质平台分子（HMF、糠醛、愈创木酚、香草醛、木质素二聚体等，RDKit 均可处理其 SMILES）编码为预训练指纹，喂给浅层模型做**小样本性质预测**（如高位热值、热重参数、溶解性、催化转化得率）——这正是"低数据药物发现"思路对能源/材料分子的平移，且与 bofire 的分子核代理（Tanimoto GP）互补。
- **迁移注意**：预训练语料是类药物分子分布，生物质分子（糖/呋喃/酚类）分布不同，直接使用有分布偏移，需领域微调；预训练权重托管在 Google Drive 外部链接，无版本管理；下游示例全是 notebook 形态，封装成服务需重写为脚本。
- **结论**：只参考。若实验田维护者后续明确要"小样本分子性质预测"能力，再按 bofire 同级评估封装（PyTorch 依赖 + 权重下载 + 脚本化重写，成本中等）。

---

## 四、落地建议

1. **优先封装 bofire**（进 MCP）：两个 command（`bofire_suggest` / `bofire_update`）+ `bofire_check` 降级探针，契约返回 `{ok, ...data, source}`；Domain/Strategy JSON 落实验记录库。
2. **ReLeaSE 只留思想**：把"预训练-预测器-RL"范式记入 Lumo 知识库，不碰代码。
3. **smiles-transformer 挂起**：记录为"小样本分子性质预测"候选能力源，触发条件出现再评估。
4. 三个库都不改变主流程，本报告仅落 docs（工单 E-02 只读调研）。

---

## 五、可执行验收

```bash
# 1. 三库全标注（进MCP封装/只参考）
grep -c "进MCP封装" docs/academic/lumo-molec-授粉报告.md      # ≥1（bofire）
grep -c "只参考" docs/academic/lumo-molec-授粉报告.md          # ≥2（ReLeaSE/smiles-transformer）
grep -c "不采用" docs/academic/lumo-molec-授粉报告.md          # ≥1（结论表列头语义）

# 2. 结论表完整（表头 + 3 行）
grep -c "^| \*\*bofire\*\*" docs/academic/lumo-molec-授粉报告.md       # ≥1
grep -c "ReLeaSE.*只参考" docs/academic/lumo-molec-授粉报告.md          # ≥1
grep -c "smiles-transformer.*只参考" docs/academic/lumo-molec-授粉报告.md  # ≥1

# 3. ReLeaSE 迁移成本专项段落存在
grep -c "Jupyter notebook 形态对封装的影响" docs/academic/lumo-molec-授粉报告.md  # ≥1

# 4. bofire×实验设计结合段落存在
grep -c "与实验田维护者实验设计流程的结合" docs/academic/lumo-molec-授粉报告.md  # ≥1
```

---

*授权：BSD-3/MIT → 主仓 AGPL v3 允许直接吞与封装。本报告仅授粉（只读调研，未复制整段代码、未动主仓），源码归档待后续工单拉取。*
