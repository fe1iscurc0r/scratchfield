# FLoRa → 龙雀 LoRa 调度设计稿（工单223 任务二）

> 日期：2026-10-09 ｜ 论文：**arXiv 2610.09226v1**《FLoRa: Flight-Assisted Data Collection from Duty
> Cycling LoRa Nodes under Energy Constraints》（PDF 全文 20 页已精读，VIP 公式逐字核对式 7）。
> 对口硬件：龙雀 NR11（ESP32-S3 移动网关背包节点）+ Ra-01（SX1278 休眠端节点）。

## 1. 论文三层架构拆解

```
┌───────────────────────────────────────────────────────┐
│ L1 路径层（离散组合优化）：Simulated Annealing           │
│    决定"访问哪些节点、什么顺序"——tour z = (z₁,z₂,…,zₙ)  │
├───────────────────────────────────────────────────────┤
│ L2 定位层（连续全局优化）：CMA-ES                        │
│    决定"在每个节点附近哪里悬停"——-hover 位置最大化链路质量│
├───────────────────────────────────────────────────────┤
│ L3 探测层（不确定性序贯决策）：constrained POMDP         │
│    决定"探几次、何时放弃"——belief 更新 + 拉格朗日松弛软约束│
└───────────────────────────────────────────────────────┘
统一目标：最大化总期望 VIP，受 UAV 电池硬预算约束
```

**分层理由**（论文原意）：三类异构优化——离散路由/连续定位/序贯决策——任何单一方法都不可解
（ curse of dimensionality）；**硬电池约束只在 L1/L2 层精确追踪，L3 松弛为软均值约束**（拉格朗日）。

## 2. ⭐ VIP 指标（论文式 7 原文核对）

> Let Vᵢ be the random variable representing the VIP at i-th IoTD visited in tour z.
> **The VIP metric is defined as:**
>
> ```
> Vᵢ = T − Σⱼ₌₁ⁱ τⱼ    if collected and Σⱼ₌₁ⁱ τⱼ ≤ T     （成功：剩余新鲜度）
>    = −τᵢ              otherwise                        （失败：浪费的时间惩罚）
> ```
> 其中 τᵢ penalizes a failed attempt by the time spent at that node.

要点（论文原文语义，防误读）：
- **T 是新鲜度时窗**（time-based data freshness decays）——收集越晚，数据价值越低；
- **失败惩罚 = −τᵢ**（不是固定罚分，是**按浪费时间计罚**）→ 优化器自然学会"别在低概率节点死等"
  （imposing well-posedness and preventing indefinite probing when an IoTD is off——摘要原话）；
- 与经典 VoI 的区别：**VoI 只给成功赋值，VIP 显式给失败赋负值**（pull-based 系统的关键修正）。

## 3. 降维映射（UAV 场景 → 龙雀场景）

| 论文概念 | 龙雀对应 | 说明 |
|---|---|---|
| UAV（飞行收集者） | **NR11 移动网关**（ESP32-S3 + SX1278 背包，可携带巡检） | "飞行"→"巡检路径"（步行/车载/云台搭载） |
| 休眠 IoTD（duty-cycling 节点） | **Ra-01 节点**（SX1278 + 深度睡眠，SPEC-20 v1.5 的 GPS+深睡版） | 占空比调度一致 |
| 悬停定位（CMA-ES 连续优化） | **驻留点选择**（网关在某节点附近停留的位置/时长） | 无飞行自由度 → 退化为离散驻留点枚举 |
| 电池硬约束（UAV） | NR11 电池（巡检时长）+ Ra-01 各自能量预算 | 双侧约束 |
| probe（探测一次） | 一次 LoRa unicast 轮询 + 等 ACK/数据 | 同构 |

## 4. 可实现版本：无 UAV 退化解

**场景 A：固定中继轮询**（NR11 部署在固定点，当"基站"用）：
- L1 路径层退化为**轮询顺序调度**（节点序列已知，退化为 TSP 小规模枚举/贪心）；
- L2 定位层**整层砍掉**（位置固定）；
- L3 探测层保留：**占空比调度下的 POMDP**——节点醒/睡不可观测（belief 建模），决定对每节点重试几次。

**场景 B：巡检采集**（NR11 被携带走一条巡检路线）：
- L1 = 巡检路线上的**访问子集选择 + 顺序**（SA 或小规模枚举均可）；
- L2 = 每节点**驻留时长**（连续量，CMA-ES 可用可简化为网格搜索）；
- L3 完整保留。

### 节点级 POMDP 表（场景 A/B 通用，L3 层）

| 要素 | 定义 |
|---|---|
| **状态 s** | 节点真实模式：`{AWAKE_rx, AWAKE_tx, SLEEP(t_rem)}` + 该节点**数据年龄** aᵢ（自上次成功收集起） |
| **观测 o** | `probe` 后：`{ACK+data / silence}`——silence 可能是"睡着"或"链路丢包"（不可分辨 → 部分可观） |
| **信念 b** | 对节点醒/睡的后验（用占空比调度表先验 + 历次 probe 结果贝叶斯更新） |
| **动作 a** | `{probe(节点 i), skip(节点 i), end_tour}` |
| **奖励 r** | **VIP 式 7**：成功 → `T − 累计耗时`；失败 → `−τᵢ`（τ = 本次 probe 耗时，含重试等待） |
| **约束** | 电池硬约束在 L1/L2 处理（网关侧：总巡检时长预算）；L3 用拉格朗日软约束（论文同法） |
| **终止** | 巡检时间窗尽 / 全节点数据年龄 < T / 连续失败熔断（对齐总线熔断思路） |

**信念更新速记**：probe 得 silence → `P(awake) ← P(awake) × P(silence|awake)` 归一化
（P(silence|awake) ≈ 链路丢包率 p_loss，可在线估计）；连续 k 次 silence 且 P(awake) < 阈值 → skip。

## 5. 与 rf_brain（skill）决策层的对接点

- **VIP 是 rf_brain 的调度评分函数**：`tools/rf_brain`（radio 域）的下一跳/采集决策处直接用式 7
  打分（不引入 POMDP 求解器——先用 belief 阈值启发式，见上）；
- **三层映射到现有代码**：L1 对应 rf_brain 的链路/路由规划 skill；L3 的 probe 重试逻辑对应
  radio_suite 的发送重试；**对接点 = rf_brain 的"下次采集谁"决策入参加 VIP 分**；
- LoRaCanary 的占空比调度表（SPEC-20 v1.5 深睡设计）是 belief 先验的数据源。

## 6. 边界

- 设计稿级，未实跑；POMDP 用启发式（belief 阈值）而非精确求解——论文用的是 POMCP 类方法，
  ESP32 侧算力不允许，退化为启发式是刻意的；
- VIP 公式为论文式 7 逐字核对；T/τ 的具体取值需龙雀实测（占空比周期、probe RTT）标定；
- CMA-ES 在场景 B 只对"驻留时长"一维优化——杀鸡用牛刀，网格搜索即可（如实标注）。
