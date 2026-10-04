# W97-03 · VIO 开源生态参考组快速勘察（voxel_svio + dm-vio）

**上游**：
- ZikangYuan/voxel_svio（827★ · GPL-3.0 · RA-L'25，无修订直接接收）
- lukasvst/dm-vio（1225★ · GPL-3.0 · RA-L'22，TUM）
**勘察方式**：GitHub 浅克隆（D:\wo34-recon\{voxel-svio,dm-vio}）+ README/目录阅读
**工单**：第三十四期扩轮卷97 · W97-03【评估·两件一报告】

---

## 1. 两件定位

| 件 | 方法族 | 亮点 | 许可 |
|---|---|---|---|
| Voxel-SVIO | MSCKF 系立体 VIO | **voxel 地图管理**（特征/地图体素化，内存与查询效率） | GPL-3.0 |
| DM-VIO | 直接法（DSO 系）VIO | **延迟边缘化**（缓解直接法线性化点过早问题）；ROS wrapper + Realsense live demo | GPL-3.0 |

结构实测：voxel-svio = config/include/src/launch/rviz_cfg/thirdLibrary（ROS 包形态，C++ 25+21 头，体量小）；
dm-vio = cmake/configs/src/test/thirdparty（非 ROS 核心 + 独立 ros wrapper 仓 dm-vio-ros）。

## 2. 各自借鉴点（GPL-3.0 只参考设计不抄代码）

### voxel_svio
1. **voxel 地图管理**：占据/特征查询的体素化组织——与 W97-01 借鉴点 3（占据距离场）
   同源，二者合并为「voxel 距离场」统一设计参照。
2. **MSCKF 轻量后端**：相比因子图优化（Kimera/gtsam），MSCKF 计算量小——
   若未来做端侧/嵌入式 VIO，MSCKF 系是算力友好路线参照。
3. RA-L'25「无修订接收」的工程完整度：config/launch/rviz 三件套齐全，ROS 包组织规范。

### dm-vio
1. **延迟边缘化思想**：线性化时机管理——对任何滑动窗口估计器（含本仓未来
   光流/IMU 融合）都是设计级参照（何时 marginalize 是精度关键）。
2. **ROS wrapper 独立仓**（dm-vio-ros）：核心算法与 ROS 绑定分离——本仓算法模块
   「纯 C++ 核心 + 绑定层分离」惯例（同 firmware 纯 C++ 三件套）的外部印证。
3. **Realsense live demo 文档**：真机接入文档范式（标定→噪声→settings.yaml）。

## 3. VIO 选型对照表（Kimera vs voxel_svio vs dm-vio）

| 维度 | Kimera-VIO | Voxel-SVIO | DM-VIO |
|---|---|---|---|
| 许可 | **BSD-2** | GPL-3.0 | GPL-3.0 |
| 视觉前端 | 特征法（立体/单目） | 特征法（立体） | 直接法（灰度梯度） |
| 后端 | 因子图（gtsam） | MSCKF + voxel 地图 | 延迟边缘化滑窗 |
| 地图输出 | metric-semantic mesh | voxel 地图 | 稀疏点云 |
| 生态/文档 | 最成熟（性能报告公开） | 中等（RA-L'25 新） | 成熟（ROS wrapper/live demo） |
| 算力需求 | 高 | 中 | 中高 |
| 本仓判定 | **首选参照（BSD 可融合）** | voxel 距离场设计参照 | 边缘化时机设计参照 |

结论：**BSD 的 Kimera 作融合候选，两件 GPL 仅作设计参照**；三者共同指向
「状态估计层接口 + 占据/距离场 + 标定档案」三件套设计（与 W97-01 合并落地）。

## 4. GPL 边界标注

- GPL-3.0：不抄代码、不并主仓；设计思想（voxel 管理/延迟边缘化）可自由借鉴。
- 若未来确需代码级使用 GPL VIO：独立进程/独立仓隔离（GPL 义务不渗入主仓），
  或等 BSD 替代（Kimera）满足需求。

## 5. 执行清单

- [x] 两件克隆 + 借鉴点 + 三件选型对照表 + GPL 边界
- [ ] （后续工单）voxel 距离场 + 状态估计接口契约（与 W97-01 合并设计文档）
