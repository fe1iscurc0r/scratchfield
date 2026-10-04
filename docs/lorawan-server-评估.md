# lorawan-server 评估（W71-11）

> 上游：mlora/lorawan-server（Gitee，11★，Erlang）｜ <https://gitee.com/mlora/lorawan-server>
> 许可：MIT（上游 gotthardp/lorawan-server 为 MIT；Gitee mirror 需最终核对，暂标待核）

## 1. 项目定位

**LoRaWAN 网络服务器**（Erlang 实现，高并发）——LoRaWAN 星型网络的服务端：管理网关、端设备、
会话（Join/ABP）、上行/下行数据路由。

## 2. 架构拆解

- **星型拓扑服务端**：网关汇聚 → 服务器解析 LoRaWAN 帧 → 路由到应用。
- **会话管理**：OTAA 入网（Join）与 ABP 激活，维护 DevAddr/会话密钥。
- **Erlang 高并发**：轻量进程模型，天然适配大量端设备并发连接。

## 3. 与本仓对照

| 维度 | lorawan-server | 本仓 |
|---|---|---|
| 拓扑 | LoRaWAN 星型（服务器中心） | LoRaCanary mesh（对等）|
| 协议 | LoRaWAN（标准） | 自研轻量帧 |

**「LoRaWAN vs mesh」协议选择结论（验收项）**：LoRaWAN 适合「运营商级、海量设备、标准互通、有服务器」
场景；mesh 对等适合「无基础设施、自组网、本地自治」场景。**LoRaCanary 走对等 mesh 与自研帧，
LoRaWAN 作为「需标准互通/网关侧」的补充**，二者按场景选，不互相替代。

## 4. 可落地借鉴点（≥3）

1. **会话/入网管理**：OTAA Join + 会话密钥轮换，借鉴给 LoRa mesh 的节点认证/密钥管理（安全增强）。
2. **网关汇聚 + 上行路由**：网关→服务器的帧汇聚与路由，借鉴给 LoRaCanary 网关侧的多节点汇聚。
3. **Erlang 高并发模型**：大量设备并发连接的处理范式，借鉴给 LoRa 网关的高并发接入设计（思想级）。

## 5. 许可裁定

MIT（待最终核对）——**可借鉴代码**；但 LoRaWAN 协议栈与本仓自研帧差异大，借鉴以「会话管理/网关路由」
设计为主，非整体移植。

## 6. 结论

可借鉴（网关/安全侧）。建议：借鉴其会话管理与网关汇聚设计，增强 LoRaCanary 网关的节点管理；协议层
维持自研帧（不引入 LoRaWAN 依赖）。
