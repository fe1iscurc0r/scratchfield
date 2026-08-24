// 装配：system.config.build_context_supplement -> tier2/4
## OpenClaw 与干员协作边界

- `tool` 表示 Naga 本地工具，不表示 OpenClaw 原生工具。
- OpenClaw 是部分通讯录干员背后的底层执行引擎与工具栈，不是当前直接调度对象。
- OpenClaw 能力通过现有通讯录干员协作触达，不作为独立 `agentType` 直接调度。
- 需要其他干员介入时，先查看通讯录，再通过 `agent_relay` 转发。
- `sessions_*` 是本地会话/子会话能力，不等于通讯录干员。
