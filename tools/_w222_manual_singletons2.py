"""工单222 任务三 · 第二批特殊形状（`X is None or X.is_closed`）手工加锁。"""
import pathlib

EDITS = [
    (
        "agentserver/agent_server_parts/search.py",
        "_search_http_client: httpx.AsyncClient | None = None\n",
        "_search_http_client: httpx.AsyncClient | None = None\n_search_http_client_lock = threading.Lock()\n",
        '''def _get_search_client() -> httpx.AsyncClient:
    """搜索代理共享 httpx 客户端"""

    global _search_http_client
    if _search_http_client is None or _search_http_client.is_closed:
        _search_http_client = httpx.AsyncClient(timeout=30.0, proxy=None)
    return _search_http_client''',
        '''def _get_search_client() -> httpx.AsyncClient:
    """搜索代理共享 httpx 客户端（工单222 任务三：并发首建加锁，防重复建连）。"""

    global _search_http_client
    if _search_http_client is None or _search_http_client.is_closed:
        with _search_http_client_lock:
            if _search_http_client is None or _search_http_client.is_closed:
                _search_http_client = httpx.AsyncClient(timeout=30.0, proxy=None)
    return _search_http_client''',
    ),
    (
        "apiserver/agentic_loop_parts/executor_openclaw.py",
        "_shared_openclaw_client: httpx.AsyncClient | None = None\n",
        "_shared_openclaw_client: httpx.AsyncClient | None = None\n_shared_openclaw_client_lock = threading.Lock()\n",
        '''def _get_openclaw_client() -> httpx.AsyncClient:
    """获取或创建共享的 httpx 客户端（避免每次调用都新建连接）"""
    global _shared_openclaw_client
    if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
        _shared_openclaw_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=150.0, connect=10.0),
            proxy=None,  # localhost 请求不走系统代理
        )
    return _shared_openclaw_client''',
        '''def _get_openclaw_client() -> httpx.AsyncClient:
    """获取或创建共享的 httpx 客户端（避免每次调用都新建连接）。

    工单222 任务三：并发首建加锁，防重复建连/连接泄漏。
    """
    global _shared_openclaw_client
    if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
        with _shared_openclaw_client_lock:
            if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
                _shared_openclaw_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=150.0, connect=10.0),
                    proxy=None,  # localhost 请求不走系统代理
                )
    return _shared_openclaw_client''',
    ),
    (
        "apiserver/routes/lumo_proxy.py",
        "_vision_client = None\n",
        "_vision_client = None\n_vision_client_lock = threading.Lock()\n",
        '''def _get_vision_client():
    global _vision_client
    import httpx
    if _vision_client is None or _vision_client.is_closed:
        _vision_client = httpx.AsyncClient(base_url=_VISION_BASE_URL, timeout=120.0)
    return _vision_client''',
        '''def _get_vision_client():
    """视觉上游共享 httpx 客户端（工单222 任务三：并发首建加锁）。"""
    global _vision_client
    import httpx

    if _vision_client is None or _vision_client.is_closed:
        with _vision_client_lock:
            if _vision_client is None or _vision_client.is_closed:
                _vision_client = httpx.AsyncClient(
                    base_url=_VISION_BASE_URL, timeout=120.0)
    return _vision_client''',
    ),
]

for path, decl_old, decl_new, body_old, body_new in EDITS:
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    assert decl_old in s, f"{path}: 声明锚点未命中"
    assert body_old in s, f"{path}: 函数锚点未命中"
    s = s.replace(decl_old, decl_new, 1)
    s = s.replace(body_old, body_new, 1)
    if "import threading" not in s:
        lines = s.splitlines(keepends=True)
        at = max(i for i, ln in enumerate(lines)
                 if ln.startswith("import ") or ln.startswith("from "))
        lines.insert(at + 1, "import threading\n")
        s = "".join(lines)
    p.write_bytes(s.replace("\r\n", "\n").encode("utf-8"))
    print("✓", path)
