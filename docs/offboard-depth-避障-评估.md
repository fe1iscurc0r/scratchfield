# W97-02 · LEE-YOONSU/offboard_rail_following 勘察（深度相机避障 PX4 管线）

**上游**：LEE-YOONSU/offboard_rail_following_drone（0★ · MIT · 2026-09-02 刚活跃）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\offboard-rail-following）+ README（韩文）/目录阅读
**工单**：第三十四期扩轮卷97 · W97-02【评估】

---

## 1. 项目定位

PX4 + MAVROS + 深度相机避障的**完整可跑管线**（铁路巡检跟随场景）：
- `unstructured_road_test/`：ROS 2 Humble + MAVROS + YOLO + depth 避障的非结构化道路试验代码；
- `railway_world/`：Gazebo Harmonic 500m 韩国铁路合成世界 + X500 下视相机模型 +
  合成数据捕获工具；数据集以 Release（datasets-20260820）分发。
星数虽 0，但 **MIT + 刚 push + 直接对口**（连续四轮「实时视觉避障」缺口的第一个可落地对照）。

## 2. 架构拆解（顶层实测）

```
unstructured_road_test/   # ROS2 Humble 包：YOLO 检测 + 深度图避障 + MAVROS offboard 控制
railway_world/            # Gazebo Harmonic 世界 + 捕获脚本（check_environment.sh/run.sh）
（数据集：GitHub Release，仓内不含）
```

要点：
- **检测（YOLO）+ 深度（depth）+ 控制（offboard）三段分离**：避障决策只吃
  「目标框+深度→障碍距离」，控制层只吃速度指令——分层干净，便于替换任一段。
- **合成世界即测试床**：Gazebo 铁路世界 + 捕获工具 = 无真机也能产出训练/验证数据；
  与 heard 的 FITL 思路同源（仿真先行）。
- **环境自检脚本**（check_environment.sh）：ROS/Gazebo 版本自检先行，降低复现成本。

## 3. 避障管线提取方案（可复用到 PX4 SITL）

1. **接口契约**：`obstacle_distance = depth_at(bbox)` → 反应式速度指令（停/绕/减速）；
   本仓避障模块按此契约实现，YOLO 可换任意检测器（含未来端侧模型）。
2. **SITL 复用**：railway_world 的 Gazebo 世界 + X500 模型可直接进 PX4 SITL 流程，
   在天选7 上跑「合成铁路/道路」避障回归（无真机闭环的第一块拼图）。
3. **数据捕获工具**：合成数据集生成脚本照搬思路（场景参数化 + 自动落盘 + Release 分发）。

## 4. 与 DDPG-AirSim（上轮已立）的互补定位

| 维度 | DDPG-AirSim（上轮） | offboard_rail_following（本轮） |
|---|---|---|
| 方法族 | 强化学习（DDPG）端到端控制 | 检测+深度+反应式控制（模块化） |
| 仿真器 | AirSim | Gazebo Harmonic |
| 可解释性 | 低（策略网络） | 高（分段可替换） |
| 落地门槛 | 高（训练算力/奖励设计） | 低（规则+检测器即可跑） |
| 定位 | 研究路线（长期） | **工程落地路线（短期首选）** |

结论：**短期走模块化反应式避障（本仓），DDPG 作长期研究对照**；二者共享 SITL 仿真层。

## 5. 许可裁定

- **MIT**：可融合（保留版权声明）；数据集 Release 使用按其 Release 说明（默认可研究用）。
- 韩文 README 不影响代码阅读；关键脚本为 Python/ROS 标准结构。

## 6. 执行清单

- [x] 克隆 + 管线拆解 + SITL 复用方案 + DDPG 互补定位
- [x] 借鉴点 3 条（契约/SITL/数据捕获）
- [ ] （后续工单）PX4 SITL 避障回归骨架（天选7）+ 障碍距离契约实现
