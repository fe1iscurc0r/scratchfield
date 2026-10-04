# W68-07 easyeda-agent 对照评估

> 上游：github.com/zhoushoujianwork/easyeda-agent · 许可 MIT（API 误标 NOASSERTION，LICENSE 文本为 MIT）· 338★ · Go · 2026-09-01 活跃
> 落点：docs/easyeda-agent-对照.md · 勘察/对照

## 1. 项目定位

嘉立创 EDA 专业版（EasyEDA Pro）的 **AI 原生自动化层**：把官方 EasyEDA 扩展 API 变成一套**有类型、可观测、Skill 友好**的动作系统。原理图全流程（S0–S6：方案书→分页→分区→摆放→布线→机械门禁→交付）已上线，PCB 流程（P0–P10）演进中。

## 2. 架构拆解

- **三层**：EasyEDA 连接器插件（极薄，桥接官方 `eda.*` 86 命名空间）+ Go CLI/daemon（协议/状态/产物/校验/工作流）+ Skill（专家工作流 + 护栏）。
- **连接器**：daemon 固定监听端口 `60832`（0xEDA0），自愈重连，校验握手。
- **typed action 目录**：覆盖原理图/PCB/文档导航/板级绑定/产物导出/诊断；`debug.exec_js` 作需二次确认的逃生口。
- **核心特色**：电路块库（37 块成熟外设电路，19 ready / 13 verified）。

## 3. 与本仓对照（同源判定）

| 维度 | 上游 easyeda-agent | 本仓 easyeda-agent |
|---|---|---|
| 同源 | zhoushoujianwork 独立实现（Go daemon + typed actions） | 本仓 easyeda 侧为 **SPEC/文档/案例层面**（JLC-EDA-寄生控制链-SPEC、easyeda-custom-extensions、CASE-26/27），非完整 typed-action 实现 |
| 接入 | daemon 60832 + WebSocket + typed actions | 屏幕+API 双通道（寄生控制链） |
| 形态 | Go CLI/daemon + Skill + MCP | 自研 |

**同源判定**：**非同源**——两者都是「EasyEDA Pro 自动化」，但实现路径不同（上游走官方 `eda.*` API + daemon + typed actions；本仓走屏幕+API 双通道寄生控制）。互补关系。

## 4. 可落地借鉴点（≥3）

1. **typed action 目录设计**：把原理图/PCB 动作做成有类型、可校验、可回放的目录，比「裸 JS 执行」安全可观测——本仓 EDA 链可参考其 typed action 范式。
2. **daemon + WebSocket + 自愈重连**：固定端口 + 握手校验 + 自愈重连的稳定连接层，可借鉴到本仓 EDA 自动化。
3. **电路块库（旗舰特色）**：社区共建、署名可追的成熟外设电路库（37 块），是「不重造轮子」的复用范式。

## 5. 许可裁定 + 结论

- **许可**：LICENSE 文本为 MIT（API 误标 NOASSERTION）→ **MIT，可借鉴代码**。
- **同源 + 互补结论**：非同源、可互补。上游「typed action + daemon + 电路块库」值得借鉴设计；本仓「屏幕+API 双通道」在无官方 API 场景仍有价值。是否迁入：否（借鉴 typed action 范式 + 电路块库思路）。
