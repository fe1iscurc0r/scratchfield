# I10 MAPPO 集群编队调度方案

> 来源：`digest-gx-4a-2026-08-30.md` 授粉点 ① ｜ 优先级 P2 ｜ 落点：ESP

## 方案对象

- **2608.23123**《Distributed Trajectory Planning and Resource Allocation for Dynamic Multi-UAV Collaborative Computing》：**MAPPO + Stackelberg 主从博弈**，分布式 UAV 轨迹规划 + 资源分配，**18.58% 效率提升 + 33.77% 延迟降低**。

## 映射 ESP32 集群编队

- **框架**：MADRL（MAPPO）+ Stackelberg 博弈 → 分布式编队 + 无线资源调度。
- **场景迁移**：无人机 → 地面无人车/ESP32 节点集群；轨迹规划 → 运动规划；带宽资源 → 计算任务分配。
- **可复用**：主从博弈把「领导者（全局目标）↔ 跟随者（局部代价）」建模为 Stackelberg 均衡，适配无中心控制器的 mesh 集群。

## 模拟计划

1. 用 MAPPO 训练 ESP32 节点集群的分布式编队策略（仿真环境：多节点二维平面 + 通信半径约束）。
2. 用 Stackelberg 博弈做无线资源分配（带宽/时隙），领导者定调度、跟随者响应。
3. 指标：编队收敛时间、任务完成率、端到端延迟（对标 18.58% 效率 / 33.77% 延迟数据）。

## 结论

P2：方案成立（MADRL + 博弈已有直接迁移路径），模拟计划已列；作为 ESP32 集群编队备选，待集群规模需求明确时启动。当前不投入。
