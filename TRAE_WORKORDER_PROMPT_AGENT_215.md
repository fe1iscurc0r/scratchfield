# 工单 215 · ROS/机器人协议生态融合调研——集百家之长（micro-ROS + zenoh + rosbridge + pymavlink）

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户问"ROS 这种协议兼容做得怎么样"——盘点结论：CI-V/RS-BA1/LoRa mesh/云台 G-code 全链路已通，MQTT 探针级，A2A 纸面，**ROS/机器人协议生态是零**。趁 GLM 订阅剩两天，把这块空白的方向调研补齐。本单纯调研+设计，不引入重型依赖。

## 关键判断（用户 2026-10-08 拍板：**留好接口 + 选择性安装**）

**接口先行，安装后置，按需启用**：
- 每个协议组件（zenoh / rosbridge 客户端 / micro-ROS Agent）在仓库里落**稳定接口层**（adapter 抽象 + 配置开关），默认**不装**依赖、不进 requirements 主线
- 依赖走**可选安装**：pip extras（如 `pip install scratchpad[zenoh]`）或独立 `extras/` 说明 + 环境变量开关（如 `LUMO_ROSBRIDGE=1`），adapter 健康检查（既有机制）检测到缺依赖时打"如何装"提示而不是报错
- 场景落地（龙雀真机 / 无人机线启动 / ROS 服务器出现）时一键装上即通——接口契约在先，安装选择在后
- 仍**不接完整 ROS2 全家桶**（DDS/rclpy/nav2），只吃协议件；本仓机器人面是嵌入式异构网+apiserver 调度，不是 Linux 机器人整机栈

## 任务一（P0）：micro-ROS / Micro-XRCE-DDS 调研卡——龙雀节点的 ROS 桥

来源实测：micro-ROS/micro_ros_espidf_component（★419，Apache-2.0，ESP32 官方组件）、eProsima/Micro-XRCE-DDS-Agent（★210，Apache-2.0）、micro-ROS/micro-ROS-Agent（★203，Apache-2.0）。

1. 调研卡 `docs/ros-ecosystem-survey/micro-ros.md`：
   - XRCE 协议栈分层：Client（MCU 内）↔ Agent（主机侧）↔ DDS 网；资源占用实测数据（RAM/flash，从上游 issue/doc 挖）
   - **与 LoRa mesh 的竞争-互补分析**：XRCE 走 UDP/TCP-serial，LoRa 长距离低带宽——判断龙雀节点该用哪个传什么（控制面 vs 遥测面）
   - 落点设计：若跑通，云服上跑 Agent，ESP32 端跑 Client，apiserver 通过 Agent 的 ROS2 topic 看到节点数据——与现有 `ptz_service` 的 transport 抽象怎么并存
2. 明确标注：这是**龙雀 v1.1 板真机验证项**，本单只出设计不刷固件

## 任务二（P0）：zenoh 调研卡——比 DDS 更适合边缘的传输层

来源实测：eclipse-zenoh/zenoh（★3243，许可 NOASSERTION⚠️ EPL/ Apache 双许可待核）+ zenoh-python（★174）。zenoh 是 ROS2 社区当前热推的 DDS 替代（zenoh-bridge-ros2dds），主打低带宽不稳定链路——**这正是 LoRa/野外场景的痛点画像**。

1. 调研卡 `docs/ros-ecosystem-survey/zenoh.md`：
   - zenoh 的 pub/sub/query 三原语 + storage 抽象，与 Lumo EventBus 的 topics/dispatch 五模式逐条对表（能对上几条、哪些是 zenoh 有而 EventBus 缺的）
   - zenoh-bridge-ros2dds 的桥接模式：能否做"Lumo EventBus ↔ zenoh ↔ ROS2 世界"的中间层，让陆墨不装 ROS 也能与 ROS 节点对话
   - **许可核实为第一优先级**：NOASSERTION 必须查明实际 LICENSE 文件内容（EPL-2.0 OR Apache-2.0 双许可则可参考；若含专有条款则只读架构）
2. 与 A2A 的关系一段话：zenoh 管数据面（telemetry/streaming），A2A 管任务面（agent 协作），两者在 Lumo Bus 三层架构里各占哪层

## 任务三（P1）：rosbridge v2 协议调研卡——不装 ROS 的最低成本通路

来源实测：RobotWebTools/rosbridge_suite（★1249，BSD-3-Clause）。rosbridge 用 JSON over WebSocket 暴露 ROS topic/service/param——**如果只是想让陆墨"说 ROS 话"而不部署 ROS 栈，这是最轻的协议规范**。

1. 调研卡 `docs/ros-ecosystem-survey/rosbridge.md`：
   - rosbridge v2 协议报文格式（publish/subscribe/call_service/advertise 五类 op）——评估写一个**只实现的客户端子集**（~200 行，websocket 出站）挂在 apiserver，让前端/agent 能订阅任意 rosbridge 服务器
   - 与现有 `websocket_manager.py` 的复用关系
2. 落点优先级判断：rosbridge 客户端 vs zenoh 桥 vs micro-ROS Agent，三选一给出"第一个实装哪个"的建议+理由

## 任务四（P1）：pymavlink 现状盘点（轻量）

ArduPilot/pymavlink（★736，NOASSERTION⚠️ 实为 LGPL-3.0）是无人机线 MAVLink 的 Python 标准库。仓库已有无人机授粉报告覆盖 PX4 offboard（microdds+ROS2），但 pymavlink 未盘。

1. 半页备忘 `docs/ros-ecosystem-survey/pymavlink-memo.md`：
   - MAVLink 与 ROS/A2A 在无人机线各自的定位（MAVLink=机-地链路，ROS=机载栈，A2A=多 agent 协作）
   - 若无人机线启动，第一个该接的是 pymavlink（直连飞控）还是 PX4 offboard（ROS2）——给结论
2. 不展开调研，半页够

## 验收
- [ ] 任务一：micro-ros 卡含 XRCE 分层图/资源占用数据/LoRa 竞争-互补分析/与 ptz_service transport 并存设计
- [ ] 任务二：zenoh 卡含许可核实结论（先查 LICENSE 再写卡）、三原语对 EventBus 对表、与 A2A 分层关系
- [ ] 任务三：rosbridge 卡含报文格式拆解、三选一实装建议
- [ ] 任务四：pymavlink 半页备忘
- [ ] **新增（接口先行验收）**：本单调研卡每张末尾附"接口层草案"一节——该组件若落地，adapter 抽象的 Python 接口签名（class/方法名/参数）+ 环境变量开关名 + 可选安装命令，一页内；不写实现
- [ ] 全程零新依赖引入（调研级）；CI 绿
