# lignet → 木质素热解 ANN 授粉报告（卷101 W101-05）

- 日期：2026-09-11
- 源：https://github.com/houghb/lignet（BSD-2-Clause License，宽松许可，可借鉴融合）
- 目标：`tools/lig_ann_probe.py`（sklearn MLPRegressor 复刻 lignet 网络骨架）
- 施工分支：trae/agent-101

## 一、源→目标映射

| 源（lignet/lignet/） | 目标（本仓库） | 映射关系 |
|---|---|---|
| `learning_curve_full_net.py:33-38` 四层网络（Input→Dense 18→Dense 20→Output 线性） | `lig_ann_probe.HIDDEN_UNITS = (18, 20)` + MLPRegressor | 网络规模/层数/输出线性语义复刻 |
| `learning_curve_full_net.py:20-21` ScaledTanH（LeCun 指导，scale 2/3 × 1.7159） | `activation="tanh"` | 激活函数对应（sklearn 无 ScaledTanH，用标准 tanh 近似） |
| `learning_curve_full_net.py:47-49` adagrad + TrainSplit(eval_size=0.3) | `solver="adam"` + `validation_fraction=0.3` | 优化器换现代默认，验证划分语义一致 |
| `create_and_train.py:29` EarlyStopping(patience=100) | `early_stopping=True, n_iter_no_change=100` | 早停实践直接对应 |
| `lignet_utils.py:26 gen_train_test`（:58-65 文档化 x/y scaler） | `train_lig_ann` 的 StandardScaler 对 | 输入/输出标准化训练实践对应 |
| `benchmarking.py:3-20` ANN 与 ligpy 双引擎对照 | （探针只取 ANN 一路） | 双引擎思想记录于报告，未落地（ligpy 依赖不可得） |

## 二、核心数据结构共鸣（附源行号）

1. **网络拓扑即数据**：源把「18/20 隐层 + 线性输出」写死在 `learning_curve_full_net.py:36-44` 的 layer 列表里，是 30 维热解产物联合回归的默认配置；本探针把同一拓扑收进 `HIDDEN_UNITS` 常量，作为 `make_lignet_model` 的默认骨架。
2. **ScaledTanH 激活**：源在 `learning_curve_full_net.py:20-21` 用 `ScaledTanH(scale_in=2./3, scale_out=1.7159)`（LeCun et al. 指导值）；sklearn 无此非线性，本探针以 `tanh` 替代并在 docstring 注明替代理由——近似而非等价，属实现层诚实降级。
3. **双标准化管线**：源 `gen_train_test`（`lignet_utils.py:26`）产出 `x_scaler/y_scaler` 并在 `:58-65` 明确文档化「transform 新数据 / inverse_transform 恢复原值」的用法；本探针 `train_lig_ann/predict_lig_ann` 完整复刻这一对缩放器往返协议。
4. **早停 + 长纪元**：源 `max_epochs=4000` 配 `EarlyStopping(patience=100)`（`create_and_train.py:29-31`）；本探针默认 `max_iter=4000, n_iter_no_change=100`，同构。

## 三、难度 × 收益

- 难度：★★☆（sklearn 单文件骨架，~70 行；无新依赖）
- 收益：★★☆（木质素热解回归「标准化+早停」管道可复用于其他热动力学拟合；为双引擎对照留下接口位）

## 四、借鉴点清单（≥3）

1. 多输出联合回归（30 维产物一步预测）的层宽选择经验——18/20 隐层直接采信源的结构超参。
2. 输入/输出双标准化并用 inverse_transform 回原量纲——借鉴自 `lignet_utils.py:58-65` 的 scaler 协议。
3. 长纪元 + patience=100 早停的训练实践——借鉴自 `create_and_train.py:29`。
4. ANN/动力学模型（ligpy）双引擎对照评测的思路——记录于报告，作为后续 P1 候选（tga-kinetics 等）联动方向。

## 五、许可裁定

lignet 为 **BSD-2-Clause License**（仓库根 `LICENSE`）：宽松许可，可借鉴与融合。本探针为独立实现，未复制任何源文件代码；网络超参（18/20/0.3/100）为配置性事实的移植。裁定：**安全**。

## 六、验收

`tools/test_lig_ann_probe.py`：3 项测试全绿（结构复刻 / 合成数据 R²>0.9 训练预测往返 / 多输出形状一致）。
