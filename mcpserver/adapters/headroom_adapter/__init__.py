"""headroom_adapter — 上下文压缩（manifest 型适配器）。

历史背景：平铺模块 mcpserver/adapters/headroom.py 走的是 FastMCP `add_tool` 路径，
但 Lumo 后端不创建 FastMCP 实例，`register_adapters()` 在运行期也没有任何调用点
（git 全历史确认：只有 tests/ 里 dry-run 调过），于是 headroom / vulnclaw / memclaw /
markitdown / llm4decompile / paper_miner / context7 等平铺适配器在运行期全是死代码
——模型既看不到也调不到。

本包按该运行形态下真正生效的约定重挂一遍（同 pdf2md_adapter / semantic_web /
graphify）：目录 + agent-manifest.json + 桥接类 handle_handoff。
注册链路：scandir(**) → mcp_registry.MANIFEST_CACHE → tool_schemas._build_mcp_schemas
→ 模型原生 function calling → registry 实例化桥接类调 handle_handoff。
"""
