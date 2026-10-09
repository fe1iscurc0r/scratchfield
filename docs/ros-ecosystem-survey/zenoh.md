# ROS 生态调研 · zenoh——比 DDS 更适合边缘的传输层（工单215 任务二）

> 采集：2026-10-08 GitHub API + LICENSE/README 实读 ｜ **调研级，零代码**
> 实测：`eclipse-zenoh/zenoh` ★**3244**（Rust，push **10-08 当天**）· `zenoh-python` ★174（push 10-08）
> ⚠️ 工单给的 ★3243 已涨到 3244；两个仓库同日活跃。

---

## 1. ⭐ 许可核实（工单定第一优先级，已核）

**LICENSE 文件实读**（2026-10-08，`eclipse-zenoh/zenoh/contents/LICENSE`）：

```
apache-2.0
epl-2.0
（其后为 Apache License 2.0 全文）
```

**结论**：zenoh 是 **EPL-2.0 OR Apache-2.0 双许可**（Eclipse 基金会标准做法）。
GitHub API 报 NOASSERTION 只是自动识别不了双许可文件。**选 Apache-2.0 通路 → 可参考、可借设计**。
（zenoh-python 同为 EPL/Apache 双许可。）

## 2. zenoh 是什么（README 口径）

**pub/sub/query 三原语 + storage 抽象**的边缘传输层：面向"低带宽、不稳定链路"的
分布式数据面，ROS2 社区当前热推的 DDS 替代（`zenoh-bridge-ros2dds` 把 ROS2 话题/服务
桥到 zenoh 网，不用改 ROS2 应用代码）。主打：peer 自动发现（组播/单播/链式）、
断续链路容忍、路径上可带 storage（历史数据可查询）——**正是 LoRa/野外场景的痛点画像**。

## 3. ⭐ 三原语 × Lumo EventBus 五模式逐条对表

EventBus（`apiserver/event_bus/bus.py`，"还原 Cordis EventsService 的五种 dispatch"）
的 dispatch 模式 vs zenoh 原语：

| EventBus 模式（五 dispatch） | zenoh 侧对应 | 对上? | 备注 |
|---|---|---|---|
| publish（fire-and-forget） | `put` | ✅ | zenoh put 可选可靠性（BestEffort/Reliable） |
| subscribe（topic 订阅） | `declare_subscriber` + 回调 | ✅ | zenoh 是声明式 key 表达式（支持 `**` 通配）比 EventBus 的精确 topic 强 |
| request（请求-应答） | `get`（query） | ✅ | zenoh query 支持 consolidation/超时 |
| broadcast 语义（bus 内全员） | `put` + key 表达式广播 | 🟡 近似 | zenoh 无显式"本地总线全员"概念，靠 key 通配达成 |
| waterfall/veto（级联否决） | **无对应** | ❌ | zenoh 是数据面原语，无 veto 语义——这属应用层逻辑 |

**zenoh 有而 EventBus 缺的**：
1. **key 表达式通配**（`robot/*/telemetry`）——EventBus 只能精确 topic；
2. **storage 抽象**（路径上可配历史存储 + `get` 查询历史）——EventBus 是纯转发无存储；
3. **断续链路容忍**（peer 掉线重连、消息可持久到重连）——EventBus 是进程内总线，
   跨进程场景（我们用 event_store JSONL + 轮转）无此能力。

**结论**：EventBus 是**进程内语义总线**（有 veto/级联这类应用语义），zenoh 是**跨网数据面**——
不是替代关系，是**两层**（见 §5）。

## 4. zenoh-bridge-ros2dds 桥接模式 → "陆墨不装 ROS 说 ROS 话"的可行性

桥的形态：ROS2 主机上跑 `zenoh-bridge-ros2dds`，把该主机的 ROS2 话题/服务映射进 zenoh 网；
zenoh 网内任意 peer（包括**没装 ROS 的**陆墨 apiserver，经 zenoh-python）即可 pub/sub 这些话题。

**可行性判断：✅ 可行且是三条路里最对症的**——
- apiserver 只需 `pip install eclipse-zenoh`（纯 Python 绑定，无 ROS 依赖）；
- ROS2 侧由对方主机装桥（他们的栈他们管）；
- 中间链路 zenoh 天然适配低带宽不稳定链路（野外/LoRa 回传段之后的回程段）。

限制：桥只做**数据面**（topic/service 报文），ROS2 的行为/action 语义有损；
且 `rcl_interfaces` 等类型需对端可解析（CBOR 编码的 ROS 消息）。

## 5. 与 A2A 的关系（工单点名一段话）+ Lumo Bus 三层架构落位

**zenoh 管数据面（telemetry/streaming），A2A 管任务面（agent 协作）**：

```
┌─ 任务面 ──────────────────────────────────────┐
│ A2A（agent↔agent 任务委托/结果回传）            │  ← agent 语义层
├─ 语义总线（进程内）───────────────────────────┤
│ Lumo EventBus（五 dispatch：publish/req/veto…）│  ← 应用语义（veto 是这层的）
├─ 数据面（跨网）───────────────────────────────┤
│ zenoh（pub/sub/query + storage + 断链容忍）    │  ← 比特搬运（telemetry/流）
│   └─ zenoh-bridge-ros2dds ──► ROS2 世界        │
│   └─ （未来）XRCE Agent ────► 龙雀 DDS 侧      │
└───────────────────────────────────────────────┘
```

zenoh 在 EventBus **之下**、A2A **之侧**（同为"跨实体"但一个搬数据一个搬任务）。

## 6. 接口层草案（接口先行验收项，不写实现）

```python
# mcpserver/ros_gateway/zenoh_link.py（假想路径）
class ZenohLink(Protocol):
    """EventBus ↔ zenoh 网的单向桥（数据面）。"""
    def put(self, key: str, payload: bytes) -> None: ...                  # EventBus publish → zenoh put
    def declare(self, key_expr: str, cb: Callable[[str, bytes], None]) -> None: ...  # zenoh → EventBus
    def query(self, key_expr: str, timeout_s: float) -> list[bytes]: ...  # 历史/对端查询
    def health(self) -> dict: ...
```

- **环境变量开关**：`LUMO_ZENOH=1` + `LUMO_ZENOH_PEER`（对方 peer 地址；未设 = 不启用）
- **可选安装**：`pip install scratchpad[zenoh]`（extras = `eclipse-zenoh`；**不进主 requirements**）
- **缺依赖行为**：健康检查打"如何装"提示（工单拍板的接口先行纪律），不报错
