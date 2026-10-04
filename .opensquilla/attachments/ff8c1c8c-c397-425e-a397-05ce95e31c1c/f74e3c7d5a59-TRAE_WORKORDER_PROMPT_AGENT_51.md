# Trae 工单执行提示词 · 智能体 51（功能实现卷 TB04）

你是智能体 51，负责第十三期功能实现卷：TB04（openai_adapter stub 实现）共 1 单。只做这些，其他不碰。

第一步：必读 docs/paper-round4-2026-09-01/tb-specs/TB04-openai_adapter-stub-实现-BLOCKED-2026-09-01-.md。

**任务**：实现 voice/input/voice_realtime/adapters/openai_adapter.py 的 connect()/disconnect()/is_active()，基于真实 OpenAI Realtime API 对接；无法对接真实 API 时 mock 并显式标注（诚实降级）。补 pytest 用例，移除 BLOCKED-2026-09-01 标记。

**避坑铁律**：不引新依赖（httpx/stdlib 够用）；中文注释/输出；推 trae/agent-51 分支。

---

**交付**：实现 + 测试全过 + 移除 BLOCKED 标记，推 trae/agent-51 分支，给出执行清单。阻塞不硬做，写清原因返回。
