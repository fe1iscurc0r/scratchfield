"""工单222 任务三 · 三个特殊形状站点的手工改写（scheduler / neko_cua）。"""
import pathlib

# ---------- 1) apiserver/event_bus/scheduler.py ----------
p = pathlib.Path("apiserver/event_bus/scheduler.py")
s = p.read_text(encoding="utf-8")
old = '''_scheduler: Scheduler | None = None


def get_scheduler(bus: EventBus | None = None) -> Scheduler | None:
    """进程级单例（读 config.bus.scheduler.ticks）。"""
    global _scheduler
    if _scheduler is None:
        target_bus = bus
        if target_bus is None:
            try:
                from . import get_bus

                target_bus = get_bus()
            except Exception:  # noqa: BLE001
                return None
        ticks: List[str] = list(DEFAULT_TICKS)
        try:
            from system.config import get_config

            cfg_ticks = getattr(get_config().bus.scheduler, "ticks", None)
            if cfg_ticks:
                ticks = [str(t) for t in cfg_ticks]
        except Exception as e:  # noqa: BLE001 - 配置不可用时用默认档位
            logger.debug("[scheduler] 读取配置失败，用默认档位: %s", e)
        _scheduler = Scheduler(target_bus, ticks=ticks)
    return _scheduler'''
new = '''_scheduler: Scheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler(bus: EventBus | None = None) -> Scheduler | None:
    """进程级单例（读 config.bus.scheduler.ticks）。

    工单222 任务三：并发首建加锁（原为裸 check-then-set，两线程可各建一个
    Scheduler → 定时任务重复注册）。
    """
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                target_bus = bus
                if target_bus is None:
                    try:
                        from . import get_bus

                        target_bus = get_bus()
                    except Exception:  # noqa: BLE001
                        return None
                ticks: List[str] = list(DEFAULT_TICKS)
                try:
                    from system.config import get_config

                    cfg_ticks = getattr(get_config().bus.scheduler, "ticks", None)
                    if cfg_ticks:
                        ticks = [str(t) for t in cfg_ticks]
                except Exception as e:  # noqa: BLE001 - 配置不可用时用默认档位
                    logger.debug("[scheduler] 读取配置失败，用默认档位: %s", e)
                _scheduler = Scheduler(target_bus, ticks=ticks)
    return _scheduler'''
assert old in s, "scheduler 锚点未命中"
s = s.replace(old, new, 1)
if "import threading" not in s:
    lines = s.splitlines(keepends=True)
    at = max(i for i, l in enumerate(lines) if l.startswith("import ") or l.startswith("from "))
    lines.insert(at + 1, "import threading\n")
    s = "".join(lines)
p.write_bytes(s.replace("\r\n", "\n").encode("utf-8"))
print("✓ scheduler.get_scheduler 已加 DCL 锁")

# ---------- 2) apiserver/neko_cua.py ----------
p = pathlib.Path("apiserver/neko_cua.py")
s = p.read_text(encoding="utf-8")
old = '''_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=NEKO_AGENT_BASE.rstrip("/"), timeout=60.0)
    return _client'''
new = '''_client: httpx.AsyncClient | None = None
_client_lock = threading.Lock()


def _get_client() -> httpx.AsyncClient:
    """懒建 httpx 客户端（工单222 任务三：并发首建加锁，避免重复建连与连接泄漏）。"""
    global _client
    if _client is None or _client.is_closed:
        with _client_lock:
            if _client is None or _client.is_closed:
                _client = httpx.AsyncClient(
                    base_url=NEKO_AGENT_BASE.rstrip("/"), timeout=60.0)
    return _client'''
assert old in s, "neko_cua 锚点未命中"
s = s.replace(old, new, 1)
if "import threading" not in s:
    lines = s.splitlines(keepends=True)
    at = max(i for i, l in enumerate(lines) if l.startswith("import ") or l.startswith("from "))
    lines.insert(at + 1, "import threading\n")
    s = "".join(lines)
p.write_bytes(s.replace("\r\n", "\n").encode("utf-8"))
print("✓ neko_cua._get_client 已加 DCL 锁")
