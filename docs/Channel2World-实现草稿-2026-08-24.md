# Channel2World 实现草稿

> arXiv:2608.17544v1 [eess.SP] 18 Aug 2026 — Hyung-Joo Moon, Joonkyu Jang, Kwang Soon Kim, Seong-Lyun Kim, Robert W. Heath Jr., Chan-Byoung Chae
> 2026-08-24 · 沈遥 · 状态：实现草稿（待审阅，可拆 SPEC 派 Trae）

---

## 一、论文核心（三句话）

1. **观点翻转**：MIMO 信道不只是链路变量，而是对物理传播环境的局部 RF 观测——同一基站环境内收集的多条信道-位置样本，是对同一传播结构的多角度观测。
2. **方法**：用 Set-Transformer/Perceiver 风格的编码器，把变长集合（多条信道的多径参数）聚合成**固定大小的"无线世界嵌入"**（Kz=16 个 latent tokens，Dm=128），作为任务无关的环境先验。
3. **训练**：context-query 自监督预训练（无任务标签）——用 context 信道推断环境嵌入，再用它预测不相交 query 信道的 UE 位置和相对路径增益。冻结编码器后，嵌入直接条件化下游任务，未见环境**零微调**部署。

## 二、为什么值得抄（价值判断）

| 维度 | 论文立场 | 对用户技术栈的意义 |
|---|---|---|
| 环境依赖是无线学习的顽疾 | site-specific 微调 vs 显式环境上下文（地图/点云）都不理想 | rf-brain 的"频谱感知→决策"同样受环境漂移困扰，需要一个**从观测直接推断**的环境先验 |
| 嵌入是可复用资产 | 一个环境一份嵌入，下游任务共享 | 相当于给每个架台点/每个频段环境建"RF 指纹卡"，跨任务复用 |
| 无标签预训练 | context-query 预测，不需要任务标注 | 用户有 SDR + IC-705 + LoRa，采集原始观测便宜，打标签贵——自监督是正路 |
| 冻结编码器部署 | 下游只需轻量 head | 适合边缘部署（ESP32 不跑 Transformer，但云服/K40 生成嵌入后可以下发） |

**红线提醒**：论文是 7GHz MIMO 基站侧（4×8/8×16 阵列、OFDM、ray-tracing 工厂场景）。用户没有 MIMO 基站硬件，**直接照抄无意义**。价值在"环境级表征 + context-query 自监督"这个范式，迁移到 SDR 频谱观测域。所以本草稿分两条线：A 线忠实复现论文（验证范式），B 线迁移到 SDR 域（落地）。

## 三、关键机制拆解

### 3.1 输入表示（为什么用多径参数而不是原始信道张量）

原始上行信道张量 H ∈ C^(Nx×Ny×Nsc)，依赖天线数/阵列布局/导频配置。论文先做信道分解（3D 参数估计），得到每条路径的：

- **相对时延** τ̄（以最短路径为参考，消掉接收机定时偏置 bτ）
- **AoA** (θ̂, φ̂)（BS 中心坐标系）
- **相对增益** ḡ（以最强路径为 0 dB 参考，消掉信道公共增益尺度 ζ）
- **UE 位置** p̂（带观测噪声 εpos）

context token（7 维）：`[τ̄, sinθ, cosθ, sinφ, cosφ, ḡ, p̂ᵀ]`
query token（5 维）：`[τ̂_prop, sinθ, cosθ, sinφ, cosφ]`——位置和增益留作监督目标

**要点**：这个表示把学习架构与天线配置解耦——不同阵列配置的基站可以直接套用。迁移到 SDR 域时对应物：多径参数 ≈ 频谱观测的特征分解（峰值/带宽/方向），UE 位置 ≈ 观测位置（GPS/架台点）。

### 3.2 环境编码器（Set Transformer + Perceiver 混合）

```
context tokens（变长集合，每条信道内先 path self-attention 4 层）
    ↓ 共享线性投影到 Dm=128
Kz=16 个可训练 latent tokens（所有环境共享初始化）
    ↓ 6 层交替 [双向 cross-attention + self-attention]
Ze ∈ R^(16×128)  ← 无线世界嵌入（固定大小，与环境/信道数无关）
```

- 双向 cross-attention：latent 收集 context 信息，context 也回看 latent
- self-attention 分开 refine 两个 token 集合
- 置换不变（set 结构），信道数/路径数可变

### 3.3 估计头（预训练监督）

query token → 8 层 query-environment 双向 cross-attention → 2 层 path self-attention → 三头：

1. **per-path 位置 GMM**：每个 query 路径给一个 UE 位置的混合高斯密度（环境嵌入补上"反射面在哪"的缺失信息，把 AoA+时延的歧义消掉）
2. **相对增益回归**：共享 MLP 预测每条路径相对增益（目标含 UE 侧波动 σξ=3dB，即增益下界）
3. **per-channel 位置 GMM**：attention pooling 聚合路径 → 信道级位置密度

损失：`L = L_path_pos + 0.1·L_gain + 0.5·L_ch_pos`（负对数似然 + MSE）

### 3.4 预训练协议（为什么有效）

- 数据组织：同一环境内采样不相交的 context 集（128 信道）和 query 集（32 信道）
- query 限制在 LoS 信道（UE 位置给 BS-UE 距离参考 → 校准传播时延）
- 目标：context 嵌入必须"解释"没见过的 query 观测 → 逼迫嵌入编码环境级传播结构，而非记忆单条信道
- 数据规模：26 个随机工厂布局 × 500 BS 位置 × 2（水平镜像）= 26,000 环境，每环境平均 ~5,000 信道-位置对

### 3.5 下游协议（冻结编码器）

`y = fΨ(o_e,i, Ze)`——Ze 由目标环境 128 条 context 信道推断（**零梯度**），下游模型用全局训练数据训练，未见环境直接测。消融实验证明：Mean/Shuffled 嵌入大幅退化 → 增益来自"匹配目标环境的嵌入"本身。

**三个下游结果（复现基线）**：
- 位置估计：嵌入条件化 > Global 无条件下游；128 样本 fine-tuning 打不过嵌入，1024 样本才反超
- 波束域 CSI 重建：嵌入略优于 Global（此任务本质是插值，增益有限）
- 环境几何重建：error-aware 下 RMSE 3.91m / MAE 1.94m，能恢复主导反射面结构（角落/不连续处差）

## 四、落地路径（两条线，三阶段）

### A 线：忠实复现（验证范式，云服/天选7 可跑）

**P0 · 数据管线（Sionna 替代 Wireless InSite）**
- 论文用商业软件 Remcom Wireless InSite。开源替代：**NVIDIA Sionna**（引用 [1]，ray-tracing 模块 RT，GPU 加速，TF2/PyTorch 双后端）——这是全草稿最重的一步，卡住就全卡
- 生成配置对齐论文 Table I：7.0 GHz、工厂布局、BS 高 15m、UE 高 1.5m、最多 12 路径、≤3 次反射、衍射关
- 输出：每环境 信道-位置对 → 多径参数（时延/AoA/增益）+ 位置，落 HDF5/parquet

**P1 · 模型复现（PyTorch）**
- 按 3.2/3.3 实现：环境编码器 + 三头估计器，~9.2M 参数
- 超参：Dm=128, Kz=16, heads=4, FFN×4, 无 dropout, context=128, query=32, batch=32, λg=0.1, λch=0.5
- 误差注入：σpos=0.1m, στ=1ns, σθ=σφ=1°, σξ=3dB（error-aware 与 error-free 双条件）
- 验收：预训练验证曲线收敛（位置 NLL 接近 σmin=0.5m 下界，增益 RMSE 接近 3dB 下界）

**P2 · 下游验证**
- 任务①：信道矩阵→位置（4×8 阵列）
- 任务②：稀疏波束→全波束域重建
- 任务③：NLoS 路径 AoA→首反射点距离（GMM 回归）
- 验收：复现"嵌入 > Global"趋势；Mean/Shuffled 消融退化

### B 线：SDR 域迁移（落地，结合用户装备）

**B0 · 观测表示迁移**
- MIMO 信道张量 → SDR IQ 快照/频谱观测（IC-705 或 RTL-SDR 采集）
- 多径参数分解 → 频谱特征分解（峰值频率/幅度/带宽、方向（若有多天线或测向）、多普勒）
- UE 位置 → 观测点 GPS 坐标（NEO-6M 已有）
- context token：`[特征参数集..., 观测点坐标]`；query 预测：位置/强度

**B1 · 应用场景（按用户装备挑 2 个）**
1. **干扰/信标环境指纹**：在固定架台点采集 LoRa/APRS 频段频谱观测 → 环境嵌入 → 新架台点用少量观测推断嵌入，预测"这个点能不能通/干扰底噪水平"（架台前决策）
2. **APRS 位置辅助**：同一 BS 环境内多条上行观测 → 嵌入辅助 UE 定位（对应论文任务①，LoRa 窄带但有多径时延/强度可挖）

**B2 · 与 rf-brain 融合**
- rf-brain 现状：频谱感知 → 特征提取 → LLM 决策 → 解调 → 反馈（感知闭环）
- 融合点：环境嵌入作为 rf-brain 的**环境条件模块**——LLM 决策前注入 Ze（架台点/频段指纹），决策从"通用"变"本地点自适应"
- 落点：`radio_brain/rf_brain/` 新增 `environment_prior/` 子模块，MCP 工具暴露 `infer_env_embedding(observations) -> embedding` 和 `query_env(embedding, task) -> prediction`

## 五、技术选型与依赖

| 组件 | 选型 | 理由 |
|---|---|---|
| Ray-tracing 数据 | **Sionna** (NVIDIA, Apache-2.0) | 开源唯一可用 RT；论文引用 [1] 即 Sionna；GPU 加速 |
| 模型框架 | PyTorch 2.x | 用户栈默认；attention 手写可控 |
| 数据格式 | HDF5 + parquet | 每环境 5k 样本，26k 环境 = 1.3 亿样本级，需要列式存储 |
| 训练硬件 | 天选7 RTX 5060 8GB（9.2M 参数训练毫无压力）或云服 | 注意 Sionna RT 需要 GPU，云服无 GPU 时降级 CPU 小规模 |
| 下游 | torch 自带 | 三个任务都是 MLP/CNN/GMM head |

**依赖检查**：`pip install sionna tensorflow`（Sionna RT 模块较新版本支持 TF 后端；若云服无 GPU，先 P0 小规模验证管线，训练放天选7）

## 六、里程碑与验收（可 grep/assert）

| 里程碑 | 交付 | 验收 |
|---|---|---|
| M0 | Sionna 生成 1 个工厂布局 × 100 BS 位置数据集 | 输出文件存在；含多径参数列；`python -c` 可加载 |
| M1 | 完整 26,000 环境数据集（或降级 2,600） | 环境数 == 配置值；每环境样本数区间 [833, 9024] |
| M2 | 模型实现 + 预训练收敛 | 位置 NLL 下降趋近下界；增益 RMSE ↓ 3dB；`pytest` 架构单测过 |
| M3 | 三个下游任务复现 | 位置任务"嵌入 > Global"；Mean 消融退化；数字进报告 |
| M4 | SDR 域 B0 表示迁移 + 场景 1 原型 | 真实 IC-705/RTL-SDR 观测 → 嵌入 → 架台点预测 demo |
| M5 | rf-brain 融合 | `environment_prior/` 模块 + MCP 工具注册；rf-brain 决策链路注入 Ze |

## 七、风险与坑

1. **Sionna 是最大风险**：Wireless InSite 是商业软件，Sionna RT 是否能量产 26k 环境规模需先验证。**M0 先行**，2 天试不出来就换简化几何（自写镜面反射追踪器，工厂场景主要是矩形反射面，实现不复杂）。
2. **论文细节缺失**：AoA 估计器（3D 参数估计）论文没给实现，说"existing tensor-based estimators"。复现时用 Sionna 自带多径输出（RT 直接给路径参数）绕过——**这是关键 hack**：RT 数据天生带 ground-truth 路径参数，不需要自己跑参数估计。
3. **数据量**：26k × 5k = 1.3 亿样本对，天选7 训练太久。降级策略：M2 用 2,600 环境（10%），验证范式后再扩。
4. **B 线表示对齐**：SDR 频谱观测没有 MIMO 阵列的 AoA 维度，迁移后"环境嵌入"的信息量上限降低。预期效果打折，管理预期。
5. **用户红线**：业余 V/U 段明文（不加密），采集仅限自己设备/架台点；LoRa 433 私网才可加密。

## 八、给 Trae 的工单拆分建议（审阅通过后）

- T1（P0）：Sionna 工厂数据集生成器——对齐 Table I 参数，输出多径参数 HDF5 + 数据卡
- T2（P1）：Channel2World 模型——环境编码器 + 三头，PyTorch，预训练脚本 + 收敛日志
- T3（P2）：三下游任务评估——位置/波束重建/几何重建，出对比表
- T4（B0/B1）：SDR 表示迁移——特征分解模块 + 场景 1 demo（真机）
- T5（B2）：rf-brain 融合——environment_prior 模块 + MCP 工具

依赖顺序：T1 → T2 → T3（A 线串行）；T4 依赖 T2 的编码器代码但不依赖 T3；T5 依赖 T4。
