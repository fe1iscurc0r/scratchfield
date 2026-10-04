# TB04 openai_adapter stub 实现（2026-09-01 完成）

> 批次：第十三期 · 专项工单
> 组装：实验田维护者（Hermes）2026-09-01

【SPEC】实现 voice/input/voice_realtime/adapters/openai_adapter.py 的 connect()/disconnect()/is_active()：基于真实 OpenAI Realtime API 对接，补充客户端初始化、状态管理、错误处理；无法对接真实 API 时 mock 并显式标注。

【验收】pytest 新增用例全过；接口可用（真机或 mock 标注）；移除 BLOCKED 标记。

【工单】① 读现有 stub ② 实现 connect/disconnect/is_active ③ 补测试 ④ 移除 BLOCKED 标记并提交。

---

【完成记录 2026-09-02】智能体 51：connect()/disconnect()/is_active() 已基于 OpenAI Realtime API（websockets，requirements 既有依赖）实现真实对接——握手带 Authorization/OpenAI-Beta 头、成功后发 session.update 配置 voice 与转写；api_key 缺失/占位、websockets 不可用、网络或认证失败时诚实降级 mock 并在 get_status().mode='mock' 显式标注。manual_interrupt 顺手真实化（response.cancel）。新增 tests/test_openai_adapter.py 11 用例全过（离线 FakeWS 打桩）。BLOCKED 标记移除。
