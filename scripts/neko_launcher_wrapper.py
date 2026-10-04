# [local-patch] NEKO × 陆墨融合 - 补齐1：launcher wrapper
# 功能：
#   1. 从 SERVERS 列表移除 memory_server 条目（陆墨侧 summer_memory 接管）
#   2. patch uvicorn.run 拦截 monitor host（0.0.0.0 -> 127.0.0.1）
#   3. 铁律8：注入 lumo provider overlay（不修改 NEKO 源码 api_providers.json）
#   4. 调用 start_launcher() 进入原有启动流
# 详见 .upstream-sha 的 local-patch 记录。

import json
import os
import sys

# 铁律7：fail-fast 凭证。环境变量未设置直接退出，禁止含默认值。
_LUMO_PROXY_TOKEN = os.environ.get("LUMO_PROXY_TOKEN", "").strip()
if not _LUMO_PROXY_TOKEN:
    print("FATAL: LUMO_PROXY_TOKEN not set.", file=sys.stderr)
    sys.exit(1)

# NEKO 源码根目录加入 sys.path（runtime.py 在 launcher_core 包内，
# network.py 在 config 包内，都需要 N.E.K.O/ 作为顶层包根）
_NEKO_ROOT = os.path.join(os.path.dirname(__file__), "..", "NEKO", "N.E.K.O")
_NEKO_ROOT = os.path.abspath(_NEKO_ROOT)
if _NEKO_ROOT not in sys.path:
    sys.path.insert(0, _NEKO_ROOT)


def _patch_servers_list():
    """移除 memory_server 条目。

    _CRITICAL_MODULES 是 main() 内局部变量，无法直接 patch。
    但 patch SERVERS 后，memory_server 不在 started 列表，
    _CRITICAL_MODULES 里的 "memory_server" 永远不会被命中，
    自然失效，不需要额外处理。
    """
    from launcher_core import runtime as _rt
    _original = _rt.SERVERS
    _filtered = [s for s in _original if s.get("module") != "memory_server"]
    _rt.SERVERS = _filtered
    # issue #19 fail-fast：patch 生效断言，防 silent 失效引入隐蔽 bug
    if _rt.SERVERS is not _filtered:
        raise RuntimeError(
            "[wrapper] FATAL: SERVERS patch not effective (attribute not replaced)"
        )
    if any(s.get("module") == "memory_server" for s in _rt.SERVERS):
        raise RuntimeError(
            "[wrapper] FATAL: memory_server still present in SERVERS after patch"
        )
    print(
        f"[wrapper] SERVERS patched: {len(_original)} -> {len(_filtered)} "
        f"(memory_server removed)",
        flush=True,
    )


def _patch_monitor_host():
    """patch uvicorn.run 拦截 monitor host。

    monitor 是独立进程，主进程 patch 可能不传递。
    若不生效，降级为不阻塞（monitor 是镜像流，对话不依赖它，
    断了不影响核心功能，符合降级链思维）。
    """
    bind_host = os.environ.get("NEKO_MONITOR_BIND_HOST", "127.0.0.1").strip()
    import uvicorn as _uvicorn
    _orig_run = _uvicorn.run

    def _patched_run(app, host=None, port=None, **kw):
        # 仅拦截 monitor 端口的 0.0.0.0 绑定，其他 uvicorn.run 调用不动
        try:
            from config.network import MONITOR_SERVER_PORT
        except Exception as _e:
            # 配置读取失败时不去匹配端口，直接放行原参数。
            # issue #19：降级放行可以，但不许静默——打 ERROR 留痕。
            print(
                f"[wrapper] ERROR: cannot read MONITOR_SERVER_PORT "
                f"({_e}); monitor host interception disabled",
                file=sys.stderr,
                flush=True,
            )
            MONITOR_SERVER_PORT = None
        if (
            MONITOR_SERVER_PORT is not None
            and port == MONITOR_SERVER_PORT
            and host == "0.0.0.0"
        ):
            print(
                f"[wrapper] monitor bind 0.0.0.0 -> {bind_host} (port {port})",
                flush=True,
            )
            host = bind_host
        return _orig_run(app, host=host, port=port, **kw)

    _uvicorn.run = _patched_run
    # issue #19 fail-fast：patch 生效断言
    if _uvicorn.run is not _patched_run:
        raise RuntimeError(
            "[wrapper] FATAL: uvicorn.run patch not effective (attribute not replaced)"
        )


def _patch_api_providers():
    """铁律8：注入 lumo provider overlay。

    不修改 NEKO 源码 api_providers.json，而是在运行时 monkey-patch
    api_config_loader.get_config()，将 overlay JSON 一层合并进配置缓存。
    上游更新 vendor 时 overlay 重新应用，配置不丢。

    数据流：
      NEKO 选 lumo provider → 请求发往 http://127.0.0.1:8001/persona/v1/chat/completions
      → lumo_proxy 注入陆墨人格+记忆+RAG → 上游 LLM → OpenAI 格式返回

    鉴权链：
      assist_api_key_fields.lumo = LUMO_PROXY_TOKEN
      → NEKO 从环境变量读取 token → Authorization: Bearer header
      → lumo_proxy.require_proxy_token 校验
    """
    overlay_path = os.path.join(os.path.dirname(__file__), "lumo_provider_overlay.json")
    if not os.path.exists(overlay_path):
        # issue #19 fail-fast：overlay 是铁律8 注入的载体，缺失时静默继续会
        # 让 NEKO 里选不到 lumo provider（融合功能整体失效且无任何报错）。
        print(
            f"[wrapper] FATAL: overlay file not found: {overlay_path}",
            file=sys.stderr,
        )
        raise RuntimeError(f"[wrapper] overlay file not found: {overlay_path}")

    with open(overlay_path, encoding="utf-8") as f:
        overlay = json.load(f)

    # 环境变量覆盖 lumo_proxy 的 base URL（适配不同端口配置）
    # 默认 http://127.0.0.1:8000/persona/v1（scratchpad API 服务器默认端口）
    lumo_base_url = os.environ.get(
        "LUMO_PROXY_BASE_URL",
        "http://127.0.0.1:8000/persona/v1",
    ).strip()
    if "assist_api_providers" in overlay and "lumo" in overlay["assist_api_providers"]:
        overlay["assist_api_providers"]["lumo"]["openrouter_url"] = lumo_base_url

    from utils import api_config_loader as _acl

    _orig_get_config = _acl.get_config

    def _patched_get_config(force_reload=False):
        config = _orig_get_config(force_reload)
        # 一层合并：overlay 的每个顶层 key 都是 dict（assist_api_providers 等），
        # 逐 key update 追加条目，不覆盖原有 provider。仅做一层 dict 合并，
        # 不递归嵌套（当前 overlay 结构不需要）。
        for key, value in overlay.items():
            if key.startswith("_comment"):
                continue
            if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                config[key].update(value)
            else:
                config[key] = value
        return config

    _acl.get_config = _patched_get_config
    # issue #19 fail-fast：patch 生效断言
    if _acl.get_config is not _patched_get_config:
        raise RuntimeError(
            "[wrapper] FATAL: api_config_loader.get_config patch not effective"
        )
    print(
        f"[wrapper] api_providers overlay applied: lumo provider injected "
        f"(url={lumo_base_url})",
        flush=True,
    )


def _patch_memory_server_calls():
    """patch 掉 main_server 对 memory_server 的 continue/block/sync 调用为 no-op。

    前提：_patch_servers_list 已移除 memory_server 进程条目，memory_server 不会启动。
    因此 main_server 在 select 端点里对 memory_server 的 POST 会连拒，导致 503；
    异常 handler 里的 block 调用、cloudsave import 后的 sync 调用也会刷 WARNING。
    no-op 化后 release_storage_startup_barrier 直接走 _ensure_main_server_runtime_initialized，
    不再触发 memory_server 通信。

    接缝代价（实验田维护者风险1）：wrapper 提前 import app.main_server 破坏 PR #1496 延迟优化，
    启动回归 ~1.5s 量级，silent。已知情接受。

    覆盖范围：
      - _request_memory_server_continue_startup：select 端点主路径，必 noop
      - _request_memory_server_block_startup：except 补偿路径，noop 消除刷屏
      - _sync_memory_server_after_startup_import：cloudsave import 后的同步，noop 消除 WARNING
    保留不动：
      - _request_memory_server_shutdown：退出时的清理信号，try/except 包裹且无下游影响
    """
    # H1 前置条件断言：必须先 _patch_servers_list 移除 memory_server 条目
    from launcher_core import runtime as _rt
    _remaining = [s for s in _rt.SERVERS if s.get("module") == "memory_server"]
    if _remaining:
        raise RuntimeError(
            "[wrapper] precondition violated: memory_server still in SERVERS; "
            "_patch_servers_list must run first"
        )

    # M2 import 错误处理：app.main_server 是重型模块，导入失败需 fail-fast 带上下文
    try:
        import app.main_server as _ms
    except Exception as e:
        print(f"[wrapper] FATAL: failed to import app.main_server: {e}", file=sys.stderr)
        raise

    # 关键副作用清理：app.main_server 模块级代码会在 _IS_MAIN_PROCESS=True 时设置
    # os.environ["_NEKO_MAIN_SERVER_INITIALIZED"]="1"。wrapper 在 launcher 父进程里
    # 提前 import 触发了这个标记，launcher 随后 spawn 的 main_server 子进程会继承
    # 该标记 → _IS_MAIN_PROCESS=False → on_startup 跳过 init_shared_state() →
    # shared_state.templates 未初始化 → GET / 返回 500。
    # 清除标记让 main_server 子进程正确识别为主进程。
    os.environ.pop("_NEKO_MAIN_SERVER_INITIALIZED", None)

    async def _noop_memory_server_call(reason: str = "") -> None:
        return None

    async def _noop_sync_memory_server_after_startup_import(import_result) -> None:
        return None

    # M1 保留原始函数引用，便于排障时运行时回退验证
    _ms._orig_request_memory_server_continue_startup = (
        _ms._request_memory_server_continue_startup
    )
    _ms._orig_request_memory_server_block_startup = (
        _ms._request_memory_server_block_startup
    )
    _ms._orig_sync_memory_server_after_startup_import = (
        _ms._sync_memory_server_after_startup_import
    )

    _ms._request_memory_server_continue_startup = _noop_memory_server_call
    _ms._request_memory_server_block_startup = _noop_memory_server_call
    _ms._sync_memory_server_after_startup_import = (
        _noop_sync_memory_server_after_startup_import
    )
    # issue #19 fail-fast：三个 noop patch 生效断言
    if (
        _ms._request_memory_server_continue_startup is not _noop_memory_server_call
        or _ms._request_memory_server_block_startup is not _noop_memory_server_call
        or _ms._sync_memory_server_after_startup_import
        is not _noop_sync_memory_server_after_startup_import
    ):
        raise RuntimeError(
            "[wrapper] FATAL: memory_server no-op patch not effective "
            "(some attribute not replaced)"
        )

    # LifecycleMixin patch 已移除（实验田维护者 R5）：Windows spawn 子进程不继承父进程
    # monkey-patch。降级链现在单点依赖 lifecycle.py 源码 patch，覆盖范围：
    #   - httpx.ConnectError 降级（lifecycle.py:1293, 1808）
    #   - httpx.TimeoutException 降级（lifecycle.py:1296, 1811）
    # wrapper 启动时 _verify_lifecycle_patch() 校验源码 patch 仍在。

    print(
        "[wrapper] memory_server calls patched to no-op "
        "(continue/block/sync; shutdown preserved)",
        flush=True,
    )


def _verify_lifecycle_patch():
    """fail-fast 校验 lifecycle.py 源码 patch 仍在（实验田维护者 R1 守护）。

    上游升级若覆盖 lifecycle.py 丢失 [local-patch] 降级，wrapper 启动时直接退出，
    避免 silent 失效导致 session 启动报 ConnectionError。
    """
    try:
        import inspect

        from main_logic.core import lifecycle as _lc
        src = inspect.getsource(_lc)
        # 期望至少 4 处 [local-patch] 标注（2 处 ConnectError + 2 处 TimeoutException）
        count = src.count("[local-patch] 陆墨融合")
        if count < 4:
            print(
                f"FATAL: lifecycle.py local-patch missing ({count}/4 expected). "
                "上游升级可能覆盖了 memory_server 降级 patch。",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[wrapper] lifecycle.py local-patch verified ({count}/4)", flush=True)
    except ImportError as e:
        # issue #19 fail-fast：lifecycle 不可 import 说明 NEKO 源码树异常，
        # 静默继续会让降级链悄悄失效（session 启动报 ConnectionError 才暴露）。
        print(
            f"[wrapper] FATAL: cannot import lifecycle for patch verify: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"[wrapper] FATAL: patch verify failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    _patch_servers_list()
    _patch_monitor_host()
    _patch_api_providers()
    _patch_memory_server_calls()
    _verify_lifecycle_patch()
    from launcher_core.runtime import start_launcher
    sys.exit(start_launcher())


if __name__ == "__main__":
    main()
