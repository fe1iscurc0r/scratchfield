# A26 DreamLedger 通信可靠性追踪

> 来源分组：group3-agent安全（第二批）

【SPEC】NEKO/LoRa 网关增加信用文件机制：Agent 间消息可信度记账，MQTT-SN 可靠性追踪。验收=方案 + 原型。
【工单】①读 digest-gx-4b DreamLedger 授粉点 ②设计信用文件 ③实现 ④评估。
【提示词】你是可靠性追踪 AI。读 digest-gx-4b-2026-08-30.md DreamLedger 授粉点（信用文件→Agent 通信可靠性追踪），为 LoRa 网关/NEKO 实现消息信用记账：每条消息按确认/超时记账，节点可信度滚动更新，低可信节点消息降级处理。输出 tools/message_ledger.py + 测试。验收：模拟丢包节点信用分正确下降，重路由决策生效。推 trae/agent-a26 分支。
