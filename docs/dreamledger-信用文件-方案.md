# A26 DreamLedger 通信可靠性追踪方案

> 生成：2026-08-31 · 来源：digest-gx-4b-2026-08-30 DreamLedger 授粉点（信用文件 → Agent 通信可靠性追踪）
> 目标：为 LoRa 网关/NEKO 增加「消息信用记账」机制，MQTT-SN 可靠性追踪。验收=方案 + 原型（`tools/message_ledger.py`）。
> 状态：方案 + 原型 + 测试

---

## 0. 结论速览

DreamLedger 的核心是把「预测的可靠性」变成「可审计的执行结算信用文件」——每次使用预测后对照真实结果更新信用值，低信用触发额外观测/缩短依赖。迁移到 Agent 通信：**每条消息按「确认/超时」记账，节点可信度滚动更新，低可信节点的消息降级处理（重路由/加冗余）**。原型用 EWMA 信用分 + 阈值降级 + 中继重路由，验证了「丢包节点信用下降 → 重路由生效」这条链。

## 1. 信用文件机制

| 环节 | 实现 |
|---|---|
| 登记 | `submit(msg_id, sender)` 消息进入 pending 表 |
| 结算 | `confirm(msg_id)`（ack=1）/ `timeout(msg_id)`（ack=0） |
| 可信度 | `credit[sender] = α·ack + (1-α)·credit_prev`（EWMA，α=0.3） |
| 降级 | 信用 < 0.35 → `downgraded(sender)` 为真 |
| 重路由 | 低信用节点消息走最可靠中继，高信用直连 |

## 2. 落地到 LoRa 网关 / MQTT-SN

- 网关对每个上游节点的 MQTT-SN 消息记账：收到 PUBACK/PUBLISH 确认记 ack，超时重传仍失败记 timeout。
- 信用分随节点实际丢包率滚动变化，天然反映链路质量。
- 低信用节点的消息自动：① 走更可靠中继（重路由）② 或按 A22 的降级策略加冗余副本。
- 信用文件可持久化，供审计与故障定位（对应 DreamLedger 的「可审计结算」）。

## 3. 验收对照

- ✅ 方案（§1/§2）。
- ✅ 原型 + 测试（`tools/message_ledger.py` + `tools/test_message_ledger.py`）。
- ✅ 模拟丢包节点信用分正确下降（`test_droppy_node_credit_falls_below_threshold`）。
- ✅ 重路由决策生效（`test_reroute_decision_takes_effect`：低信用走中继、高信用直连）。

## 4. 与其它工单衔接

- A22 通信退化课程：降级策略（冗余/重试）的触发信号可来自本账本的信用分。
- R50 APC-RLNC 弹性路由：重路由候选路径的可靠性评分可复用本账本。
