# ROS 生态调研 · micro-ROS / Micro-XRCE-DDS——龙雀节点的 ROS 桥（工单215 任务一）

> 采集：2026-10-08 GitHub API + README/docs 实读 ｜ **调研级，零代码，零依赖引入**
> 实测：`micro-ROS/micro_ros_espidf_component` ★419 Apache-2.0（ESP32 官方组件，push 10-02）·
> `eProsima/Micro-XRCE-DDS-Agent` ★210 Apache-2.0 · `micro-ROS/micro-ROS-Agent` ★203 Apache-2.0
> ⚠️ 定位声明：这是**龙雀 v1.1 板真机验证项**，本单只出设计**不刷固件**。

---

## 1. XRCE 协议栈分层

```
┌─────────────────────┐   ┌──────────────────────┐   ┌─────────────────────┐
│ 龙雀节点（ESP32-S3） │   │ 主机侧 Agent          │   │ DDS 网（ROS2 世界）  │
│ micro-ROS Client    │◄─►│ Micro-XRCE-DDS-Agent │◄─►│ rclpy / nav2 / …    │
│ (rclc，静态内存池)   │XRCE│ (可跑在云服/工作站)    │DDS│                     │
└─────────────────────┘   └──────────────────────┘   └─────────────────────┘
     UDP/TCP/Serial              DDS(RTPS over UDP)          RTPS
     (微控制器侧极简客户端)       (资源受限的 DDS 代理)      (标准 ROS2 通信)
```

核心思想：**MCU 上不跑 DDS**（太重），跑极简 XRCE Client；Agent 在资源充足的主机上代为
接入 DDS 网。Client 与 Agent 之间是**请求/应答式的序列化消息**（话题数据作为 payload）。

## 2. 资源占用（上游 README/docs 口径，⚠️ 非本机实测）

- micro-ROS 官方口径：Client 可跑在 **RAM 数十 KB 级**的 MCU（ESP32 完全够）；flash 占用
  ~**1-2 MB**（含 rcl/rclc 栈与序列化支持）；
- ⚠️ 如实标注：上游文档给的是"适合资源受限设备"的定性 + 社区 issue 里的经验值区间，
  **精确的 RAM/flash 数字依赖配置**（话题数/消息类型/QoS），未在本单复测——真机验证项里补。

## 3. ⭐ 与 LoRa mesh 的竞争-互补分析（控制面 vs 遥测面）

| 维度 | XRCE（micro-ROS） | LoRa mesh（现网） |
|---|---|---|
| 链路 | UDP/TCP/Serial（短距、可靠） | LoRa（**长距离、低带宽**） |
| 带宽 | Mbps 级 | kbps 级 |
| 时延 | 毫秒级 | 秒级 |
| 功耗 | 较高（WiFi/有线） | **极低**（野外电池场景） |
| 生态 | 直连 ROS2 世界 | 自有 mesh 路由（APC-RLNC 等） |

**判断（控制面 vs 遥测面）**：
- **遥测面（高频采样、传感器流）→ XRCE**：数据量大、需要低时延投递到 DDS/云侧分析；
- **控制面（低频指令、状态回传、跨野外节点）→ LoRa**：距离远、功耗预算严苛；
- **两不替代**：龙雀节点若在 WiFi 可达处（如实验台/园区），XRCE 直连 Agent；
  野外部署时 LoRa 回传，Agent 侧再桥 DDS。**同一节点可双栈**（分区固件分区预算）。

## 4. 与 `ptz_service` transport 抽象的并存设计

现状（`mcpserver/ptz_service/transport.py`）：`PTZTransport` 抽象已有
`SerialTransport / LoraBridgeTransport / SimPTZTransport` 三实现，
`service.py:251` 统一走 `transport.send(line, timeout)`。

**并存方案**：XRCE 不取代 PTZ 的 transport（那是云台 G-code 的串行/LoRa 通道），
而是**新增一个并列的数据面**：
- PTZ transport：**控制面**（云台指令，G-code 行协议，保持不变）；
- XRCE Client：**遥测面**（传感器话题 → DDS），固件里独立任务；
- 主机侧 Agent 是**新组件**（云服部署），apiserver 通过 Agent 的 ROS2 topic 订阅看到节点数据——
  对 apiserver 而言只是"多一类可订阅的数据源"，与 EventBus 的订阅侧对接（见 zenoh 卡 §5 分层）。

## 5. 接口层草案（接口先行验收项，不写实现）

```python
# mcpserver/ros_gateway/xrce_agent.py（假想路径；实际落地时定）
class XRCESession(Protocol):
    """龙雀 XRCE 遥测在主机侧的接入点（Agent 进程外，经其 DDS 侧桥入）。"""
    def topics(self) -> list[str]: ...                 # 可订阅的 ROS2 话题清单
    def subscribe(self, topic: str, cb: Callable[[dict], None]) -> None: ...
    def unsubscribe(self, topic: str) -> None: ...
    def health(self) -> dict: ...                       # 接 adapter 健康检查体系
```

- **环境变量开关**：`LUMO_XRCE_AGENT_URL`（未设 = 不启用；Agent 侧用 micro-ROS-Agent 的
  XML/WS 接口或 DDS 侧桥，真机验证项再定）
- **可选安装**：`pip install scratchpad[xrce]`（extras 只含 `websockets`，Agent 本体是独立进程）
- **缺依赖行为**：adapter 健康检查报 "micro-ROS Agent 未部署，参见 docs/ros-ecosystem-survey/micro-ros.md §5"（提示安装，不报错）
