# I01 MPC 分布式量子计算路径（远期观察）

> 来源：`digest-g4-3-2026-08-30.md` ｜ 优先级 P2 ｜ 落点：观察

## 核心发现

- **2608.23159v1**（🥇）《Taming Spacetime Overhead and Design Complexity in Distributed Fault-Tolerant Superconducting Quantum Computation》：给出分布式超导量子计算跨越模块化边界的**近尺度不变开销**，为百万量子比特规模化提供可信工程路径。
- **2608.20462v1**《To Scale Up or To Scale Out: Evaluating Space-Time Costs of Modular…》：模块化集成（chiplet vs 分布式架构）的时空成本对比，是规模化超导 QPU 的主路径评估。

## 观察结论

分布式超导量子计算的瓶颈正从「物理量子比特数」转向「跨模块连接的时空开销」。关键信号：**近尺度不变开销**——若分布式架构的连接开销随规模增长近乎不增长，则「横向扩展（scale-out）」第一次在工程上可信地替代「纵向堆料（scale-up）」。

## 触发条件（进入下一步的信号）

1. 出现 ≥1 篇给出**分布式量子互联开销随规模近常数**的实测/严格证明（而非仿真）；
2. 有厂商/实验室发布 chiplet 级超导 QPU 的**模块间纠缠保真度 ≥ 99%** 的实测数据；
3. MPC 侧：多方案（MPC 协议）能在**分布式量子节点间做安全多方计算**的量子版本被原型验证。

当前：**纯观察**，不投入实现。满足任一条触发条件后再评估是否纳入 rf_brain/量子侧 backlog。
