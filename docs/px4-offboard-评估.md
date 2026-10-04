# px4-offboard 评估（自主飞行控制层样例链）

> 2026-09-08 · 卷80 W79-04 · 评估（不写实现）
> 上游：Jaeyoung-Lim/px4-offboard（BSD-3-Clause，★288，Python microdds+ROS2）

## 一、项目定位

PX4 offboard 控制的标准样例链（setpoint 控制、轨迹跟随），是无人机自主飞行控制层的教科书级实现。

## 二、架构拆解

- 控制通道：MAVLink / microdds 双路（offboard mode）。
- 控制模式：位置/速度/姿态 setpoint 流式下发。
- 语言：Python（ROS2 生态）+ 官方 PX4 配合。

## 三、与本仓对照

GAAS 栈 offboard 控制块的对照系；本仓无人机优先方向控制层候选（BSD-3 干净可借鉴）。

## 四、可落地借鉴点（≥3）

1. **setpoint 流式下发节奏**：offboard 模式的心跳/超时管理（失联自动降落）。
2. **microdds 与 MAVLink 双通道抽象**：通信层解耦，可复用到 SITL 仿真。
3. **轨迹跟随控制律**：位置环-速度环-姿态环的参考实现。

## 五、许可裁定

BSD-3-Clause：干净可借鉴代码；接入判定——作为 PX4 SITL 仿真控制层参照直接借鉴。

---
*评估：fe1iscurc0r · 2026-09-08 · 基于上游公开文档，未 clone 源码*
