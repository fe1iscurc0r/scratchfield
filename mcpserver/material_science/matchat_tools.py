"""
MatChat MCP 工具 — 集成到 MaterialScienceAgent

用法:
    from mcpserver.material_science.matchat_tools import register_matchat_tools
    register_matchat_tools(agent_instance)

架构: 双模式桥接 (persistent 自管理浏览器 / CDP 外部浏览器)
详见 matchat_bridge.py

线程安全说明:
    Playwright sync_api 对象绑定创建它的线程，跨线程使用会报错。
    本模块通过 agent 层的单线程池（materialscience_agent._matchat_executor）
    保证所有 MatChat 调用都在同一线程执行；额外用 _bridge_lock 保护
    _matchat_bridge 的懒加载，防止并发首调创建多个浏览器实例。
"""
import logging
import threading
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# 工具名常量：供 agent 层判断是否需要路由到 MatChat 单线程池
TOOL_NAMES = [
    "matchat_search",
    "matchat_chat",
    "matchat_extract",
    "matchat_login_check",
]

# 输入长度上限：防止超长文本撑爆浏览器输入框或拖慢 DOM 提取
MAX_QUERY_LEN = 1000
MAX_MESSAGE_LEN = 8000
# max_results 合理区间：太少无意义，太多会让 AI 回复过长难解析
MAX_RESULTS_LIMIT = 20


def register_matchat_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 MatChat 工具。

    延迟加载 matchat_bridge，首次调用时启动持久化浏览器 (persistent 模式)。
    用户需在弹出的浏览器窗口中完成 MatChat 登录，登录态会持久化保存。

    Args:
        agent: MaterialScienceAgent 实例，工具以闭包形式注入到 agent.tools
    """
    # 桥接实例：首次调用 _get_bridge 时才创建，None 表示尚未初始化或已断开
    agent._matchat_bridge = None
    # 桥接懒加载锁：防止并发首调重复创建多个持久化浏览器（同 user_data_dir 会冲突）
    agent._matchat_bridge_lock = threading.Lock()

    def _get_bridge():
        """懒加载：首次调用时初始化浏览器连接。

        线程安全：用 _matchat_bridge_lock 保护，避免并发请求同时触发 connect()
        创建出多个浏览器实例（persistent 模式下多实例会争抢同一 user_data_dir 报错）。
        """
        # 快路径：已存在且仍连接，直接返回
        if agent._matchat_bridge is not None and agent._matchat_bridge.is_connected():
            return agent._matchat_bridge

        with agent._matchat_bridge_lock:
            # 双检锁：拿到锁后再确认一次，可能已被其他线程初始化
            if agent._matchat_bridge is not None and agent._matchat_bridge.is_connected():
                return agent._matchat_bridge

            from mcpserver.material_science.matchat_bridge import MatchatBridge
            bridge = MatchatBridge()  # 默认 persistent 模式
            if bridge.connect():
                agent._matchat_bridge = bridge
                logger.info("[MatChat MCP] persistent 浏览器桥接已就绪")
            else:
                # 连接失败置 None，下次调用会再次尝试连接
                agent._matchat_bridge = None
                logger.warning("[MatChat MCP] 浏览器连接失败，工具将不可用")
        return agent._matchat_bridge

    def _handle_bridge_result(result: dict[str, Any]) -> dict[str, Any]:
        """统一处理 bridge 返回结果，补充登录提示。

        bridge 在需要登录时会带 needs_login=True 但不一定有 message，
        这里补一个面向用户的友好提示，避免上层拿到空 message。
        """
        if not result.get("success") and result.get("needs_login"):
            result["message"] = result.get("message", "请在弹出的浏览器中登录 MatChat 后重试")
        return result

    # ── 四个工具 ──────────────────────────────

    def _matchat_search(params: dict[str, Any]) -> dict[str, Any]:
        """搜索材料科学文献。

        参数校验：query 非空且不超长；max_results 强制为 1~MAX_RESULTS_LIMIT 的整数。
        非法 max_results（负数/字符串）会被兜底为默认值，不让调用崩在类型转换上。
        """
        query = params.get("query", "")
        # 强制转 str：防止上层误传 int 等类型
        if not isinstance(query, str):
            query = str(query)
        query = query.strip()

        if not query:
            return {"success": False, "error": "请提供搜索关键词 query"}
        if len(query) > MAX_QUERY_LEN:
            return {"success": False, "error": f"query 过长，上限 {MAX_QUERY_LEN} 字符"}

        # max_results 容错转换：非法值回退默认 5
        try:
            max_results = int(params.get("max_results", 5))
        except (TypeError, ValueError):
            max_results = 5
        # 钳制到合理区间，避免 0 或超大值
        max_results = max(1, min(MAX_RESULTS_LIMIT, max_results))

        bridge = _get_bridge()
        if not bridge:
            return {"success": False, "error": "MatChat 浏览器未就绪 (Playwright 可能未安装)"}

        return _handle_bridge_result(bridge.search_literature(query, max_results))

    def _matchat_chat(params: dict[str, Any]) -> dict[str, Any]:
        """与 MatChat AI 对话。

        参数校验：message 非空且不超长，防止超长文本拖垮浏览器输入与回复提取。
        """
        message = params.get("message", "")
        if not isinstance(message, str):
            message = str(message)
        message = message.strip()

        if not message:
            return {"success": False, "error": "请提供对话内容 message"}
        if len(message) > MAX_MESSAGE_LEN:
            return {"success": False, "error": f"message 过长，上限 {MAX_MESSAGE_LEN} 字符"}

        bridge = _get_bridge()
        if not bridge:
            return {"success": False, "error": "MatChat 浏览器未就绪 (Playwright 可能未安装)"}

        return _handle_bridge_result(bridge.chat(message))

    def _matchat_extract(params: dict[str, Any]) -> dict[str, Any]:
        """提取当前页面内容（无入参，直接复用 bridge）"""
        bridge = _get_bridge()
        if not bridge:
            return {"success": False, "error": "MatChat 浏览器未就绪"}

        return _handle_bridge_result(bridge.extract_page_text())

    def _matchat_login_check(params: dict[str, Any]) -> dict[str, Any]:
        """检查 MatChat 登录状态（无入参，直接复用 bridge）"""
        bridge = _get_bridge()
        if not bridge:
            return {"success": False, "error": "MatChat 浏览器未就绪"}

        return bridge.ensure_login()

    # 注入工具：以闭包形式注册，避免暴露 bridge 实例
    agent.tools.update({
        "matchat_search": _matchat_search,
        "matchat_chat": _matchat_chat,
        "matchat_extract": _matchat_extract,
        "matchat_login_check": _matchat_login_check,
    })

    logger.info(f"[MatChat MCP] 已注册 {len(TOOL_NAMES)} 个工具")


def get_matchat_tool_descriptions() -> list[dict[str, Any]]:
    """返回 MatChat 工具的描述列表，用于 agent-manifest。

    供前端/调度层展示工具能力与参数说明，不参与运行时调用。
    """
    return [
        {
            "command": "matchat_search",
            "description": "MatChat 文献检索：通过 MatChat AI 搜索材料科学文献。首次使用需在弹出的浏览器中登录 MatChat。",
            "params": {
                "query": "搜索关键词（必填），如 '木质素碳化温度优化'",
                "max_results": "返回结果数（默认5）",
            },
            "example": '{"tool_name":"matchat_search","query":"lignin carbonization temperature","max_results":3}'
        },
        {
            "command": "matchat_chat",
            "description": "MatChat AI 对话：与松山湖材料实验室 AI 讨论材料合成路径、性能对比、配方优化。首次使用需登录。",
            "params": {
                "message": "对话内容（必填），如 '对比淀粉基和明胶基生物塑料的力学性能差异'",
            },
            "example": '{"tool_name":"matchat_chat","message":"如何优化木质素基碳材料的电导率？"}'
        },
        {
            "command": "matchat_extract",
            "description": "MatChat 页面提取：提取当前 MatChat 页面的文本内容（用于批量获取对话结果）",
            "params": {},
            "example": '{"tool_name":"matchat_extract"}'
        },
        {
            "command": "matchat_login_check",
            "description": "检查 MatChat 登录状态：返回是否需要登录、当前页面 URL 等信息",
            "params": {},
            "example": '{"tool_name":"matchat_login_check"}'
        },
    ]
