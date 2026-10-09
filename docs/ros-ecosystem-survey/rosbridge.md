# ROS 生态调研 · rosbridge v2——不装 ROS 的最低成本通路（工单215 任务三）

> 采集：2026-10-08 GitHub API + ROSBRIDGE_PROTOCOL.md 实读 ｜ **调研级，零代码**
> 实测：`RobotWebTools/rosbridge_suite` ★1249 **BSD-3-Clause** ✓（push 10-05，Python）

---

## 1. 协议本质

**JSON over WebSocket** 暴露 ROS topic/service/param/action——一个报文信封 `{"op": "…", …}`，
双向文本帧。**如果只是想让陆墨"说 ROS 话"而不部署 ROS 栈，这是最轻的协议规范**（工单判断成立）。

## 2. ⭐ 报文格式拆解（ROSBRIDGE_PROTOCOL.md 实读，协议已到 2.1.0）

信封：`{ "op": "<操作>", "id": "<可选，关联请求/响应>", … }`。

| op（v2.1.0 全集） | 方向 | 字段要点 | 陆墨客户端子集需要吗 |
|---|---|---|---|
| `advertise` | C→S | `topic, type`（声明我要发布） | ✅（想往 ROS 发的话） |
| `unadvertise` | C→S | `topic` | ✅ |
| `publish` | C↔S | `topic, msg`（msg 按 ROS 类型字段嵌套 JSON） | ✅ 核心 |
| `subscribe` | C→S | `topic[, type, throttle_rate, queue_length]` | ✅ 核心 |
| `unsubscribe` | C→S | `topic` | ✅ |
| `advertise_service` / `unadvertise_service` | C→S | `service, type`（客户端当服务端） | ⬜（v1 不需要） |
| `call_service` | C↔S | `service, args[, frag_id, num_frags]`（大参分片） | 🟡 可后补 |
| `advertise_action` 系列 | C→S | action 三件套 | ⬜（v1 不需要） |
| 服务端推送 `status` / `service_response` | S→C | 错误/结果回传 | ✅（收结果必须） |

编码：JSON 为主；`png/cbor/cbor-raw` 是**可选**压缩编码（advertise 时 `type` 前缀标识）——
客户端子集可只实现 JSON。

**结论：一个 ~200 行的"只实现的客户端子集"完全成立**——五个 op
（advertise/unadvertise/publish/subscribe/unsubscribe）+ status/service_response 接收，
纯 `websockets` 库出站，无任何 ROS 依赖。

## 3. 与 `websocket_manager.py` 的复用关系

现状（`apiserver/websocket_manager.py`，DCL 单例）：面向**前端客户端的 WS 服务端**（广播/推送）。
rosbridge 客户端是**出站 WS 客户端**（连别人的服务器）——**方向相反，复用的是模式不是代码**：

- 复用：心跳/重连/注册表管理的产品模式、`get_websocket_manager()` 的单例接入姿势；
- 不复用：连接对象与事件循环（一个 accept 一个 connect）。
建议独立 `RosbridgeClient` 类（不塞进 websocket_manager）。

## 4. ⭐ 三选一实装建议（工单点名）

**第一个实装：rosbridge 客户端。** 理由：

| | rosbridge 客户端 | zenoh 桥 | micro-ROS Agent |
|---|---|---|---|
| 前置条件 | 任意现成 rosbridge 服务器（ROS 社区大量现成） | 对端主机装 zenoh 桥 + peer 配置 | 需 Agent 进程 + 龙雀 v1.1 真机 |
| 依赖 | 仅 `websockets`（≈0 成本） | `eclipse-zenoh`（Rust 绑定，体积/编译考量） | C++ Agent（独立进程部署） |
| 代码量 | **~200 行**（五个 op） | 桥接层 + 类型映射（CBOR/ROS 消息解析） | 最大（DDS 侧订阅 + 转 EventBus） |
| 见效场景 | 立即：陆墨可订阅任何 rosbridge 服务器的话题 | 对端就绪后：真 ROS2 网互联 | 龙雀真机后：嵌入式遥测 |

顺序建议：**rosbridge（立即、零成本验证协议位）→ zenoh（对端出现 ROS2 主机时）→
micro-ROS（龙雀 v1.1 真机验证项）**——三者按"前置条件成熟度"自然排序，不互斥
（rosbridge 验证的应用层假设对后两者直接复用）。

## 5. 接口层草案（接口先行验收项，不写实现）

```python
# mcpserver/ros_gateway/rosbridge_client.py（假想路径）
class RosbridgeClient(Protocol):
    """rosbridge v2 客户端子集（五 op + 响应接收）。"""
    def connect(self, url: str) -> None: ...                                   # ws://host:9090
    def advertise(self, topic: str, ros_type: str) -> None: ...
    def publish(self, topic: str, msg: dict) -> None: ...
    def subscribe(self, topic: str, cb: Callable[[dict], None]) -> None: ...
    def unsubscribe(self, topic: str) -> None: ...
    def close(self) -> None: ...
    def health(self) -> dict: ...                                               # 接 adapter 健康检查
```

- **环境变量开关**：`LUMO_ROSBRIDGE_URL`（如 `ws://192.168.1.50:9090`；未设 = 不启用）
- **可选安装**：`pip install scratchpad[rosbridge]`（extras 仅 `websockets`——仓库已有，实际零增量）
- **缺依赖/断连行为**：健康检查提示 + 自动重连（借 websocket_manager 的产品模式）
