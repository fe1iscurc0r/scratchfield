# pymavlink 现状备忘（工单215 任务四 · 半页，轻量盘点）

> 采集：2026-10-08 GitHub API ｜ `ArduPilot/pymavlink` ★736（push **10-08 当天**，Python）
> 许可：GitHub 报 NOASSERTION——**实为 LGPL-3.0**（工单已注明；MAVLink 生态惯例）。
> LGPL-3.0 对"作为库引用"是**可用**的（动态/独立进程引用无传染），但**不可复制其代码进仓**——按仓内许可红线：只引用不融合。

## 三者在无人机线的定位（一句话各归位）

- **MAVLink** = **机-地链路**：飞控 ↔ 地面站的紧凑二进制遥测/命令协议（pymavlink 是其 Python 标准库）；
- **ROS**（机载栈）= **机内总线**：机载计算机（伴飞电脑）上的传感器/导航/控制图；
- **A2A** = **多 agent 协作面**：陆墨与其它 agent 的任务委托层（不上机）。

## 若无人机线启动，第一个接谁？——**pymavlink（直连飞控）**

理由：
1. **前置最轻**：一条 USB/串口/数传链路 + `pip install pymavlink`，不需要伴飞电脑、不需要 ROS 栈；
2. **覆盖第一刚需**：无人机线的第一步永远是"看得到飞机"（遥测流：姿态/GPS/电池/模式）+
   "发得了指令"（arm/takeoff/mode/setposition）——这正是 pymavlink 的全部；
3. PX4 offboard（microdds+ROS2，已有授粉报告覆盖）是**第二步**：需要伴飞电脑 + ROS2 环境，
   适合自主轨迹/视觉闭环——在"飞起来再说"之前都是过度配置；
4. **与陆墨架构对味**：pymavlink 是串口/UDP 的**直连库**——与 ptz_service 的 transport 抽象
   同构（SerialTransport 的又一个兄弟），接入面小；ROS2 则要动用 zenoh/rosbridge 的整条桥路。

一句话：**先 pymavlink 把链路打通看遥测，伴飞需求出现再上 ROS2 桥（经 zenoh 或 rosbridge），
多机协同才轮到 A2A。**

## 接口层草案（一行归位）

`pymavlink` 落地时进 `ptz_service/transport.py` 同族的 transport 抽象
（`MavlinkTransport(PTZTransport)` 风格或并列新抽象），开关 `LUMO_MAVLINK_URL`
（serial:// 或 udp://）；extras `scratchpad[mavlink]`。本单不写实现。
