"""工单222 · 并发与锁安全 —— 回归测试。

三组：
  A. config 读-改-写互斥（修复前实测 20 线程丢 19 个更新；本测试钉住"零丢失"）
  B. 懒加载单例并发首建（DCL 后必须只有一个实例）
  C. 原子写入口（atomic_write_json 不产生半截文件，失败不污染目标）

运行：CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe -m pytest tests/test_concurrency_locks.py -q
"""
from __future__ import annotations

import importlib
import json
import re
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ────────────────────────── A. config 读-改-写互斥 ──────────────────────────

class TestConfigRmwLock:
    """`system.config_manager.update_config` 的读-改-写必须全程互斥。"""

    @pytest.fixture()
    def cm_env(self, tmp_path, monkeypatch):
        import system.config_manager as CM

        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"schema_version": 2}, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(CM, "get_config_path", lambda: str(cfg))
        monkeypatch.setattr(CM, "bootstrap_config_from_example", lambda *a, **k: None)
        monkeypatch.setattr(CM, "hot_reload_config", lambda *a, **k: None)
        # 去掉 update_config 尾部的定长 sleep：本测试验证锁语义，不验证节流
        monkeypatch.setattr(CM.time, "sleep", lambda *_: None)
        return CM, cfg

    def test_concurrent_update_no_lost_update(self, cm_env):
        """20 线程 × 50 轮并发写不同字段 → 1000 个字段必须全部落盘（零丢失）。"""
        CM, cfg = cm_env
        manager = CM.ConfigManager()
        threads_n, rounds = 20, 50
        barrier = threading.Barrier(threads_n)
        failures: list[str] = []

        def worker(tid: int):
            try:
                barrier.wait()
                for r in range(rounds):
                    if not manager.update_config({f"t{tid}_r{r}": r}):
                        failures.append(f"t{tid}_r{r}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"t{tid}: {e!r}")

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(threads_n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()

        final = json.loads(cfg.read_text(encoding="utf-8"))
        expected = {f"t{i}_r{r}" for i in range(threads_n) for r in range(rounds)}
        got = {k for k in final if re.fullmatch(r"t\d+_r\d+", k)}
        assert not failures, f"update_config 失败: {failures[:5]}"
        assert expected - got == set(), f"丢失更新 {len(expected - got)} 个: {sorted(expected - got)[:5]}"
        assert got - expected == set()

    def test_rmw_lock_is_reentrant_for_nested_save(self, cm_env):
        """RLock 语义：迁移写回（_load_config_file → _save_config_file）不得自锁死。"""
        CM, cfg = cm_env
        manager = CM.ConfigManager()
        assert manager.update_config({"nested": {"a": 1}})
        assert manager.update_config({"nested": {"b": 2}})
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data["nested"] == {"a": 1, "b": 2}  # 递归合并语义保持


# ────────────────────────── B. 懒加载单例并发首建 ──────────────────────────

# (module, getter, 单例全局名) —— 工单222 任务三改写过的站点
SITES = [
    ("apiserver.device_state", "get_device_state_store", "_store"),
    ("apiserver.message_queue", "get_message_queue", "_message_queue"),
    ("apiserver.loop_checkpoint", "get_loop_checkpoint", "_cp"),
    ("apiserver.llm_service", "get_llm_service", "_llm_service"),
    ("apiserver.hil_evaluator", "get_hil_evaluator", "_evaluator"),
    ("apiserver.knowledge_driver", "get_knowledge_driver", "_driver"),
    ("apiserver.websocket_manager", "get_websocket_manager", "_ws_manager"),
    ("apiserver.von_client", "get_von_client", "_default_client"),
    ("apiserver.channels", "get_channel_registry", "_registry"),
    ("apiserver.event_bus", "get_bus", "_bus"),
    ("mcpserver.mcp_manager", "get_mcp_manager", "_MCP_MANAGER"),
    # 注意：mcpserver.mcp_server._get_chain_executor(cls, call_fn) 需要必填参数，
    # 不适用"无参并发首调"探针（其 DCL 由 codemod 统一处理，代码形状已核）。
    ("mcpserver.trust_layer", "get_trust_scorer", "_scorer"),
    ("agentserver.dogtag.registry", "get_dogtag_registry", "_registry"),
]


def _ctor_name(module_file: str, var: str) -> str | None:
    """从源码里抠出 `var = ClassName(` 的类名（用于打桩放大竞态窗口）。"""
    try:
        src = Path(module_file).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(rf"^\s*{re.escape(var)}\s*=\s*([A-Za-z_]\w*)\(", src, re.M)
    return m.group(1) if m else None


@pytest.mark.parametrize("mod_name,getter,var", SITES, ids=[s[1] for s in SITES])
def test_singleton_single_instance_under_concurrency(mod_name, getter, var):
    """16 线程同时首调 → 构造函数只允许执行一次（DCL 生效）。

    为了把竞态窗口放大到可观测，给构造函数注入 10ms 延迟
    （现实中等价于构造涉及读文件/建连接的场景）。
    """
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:  # noqa: BLE001 —— 依赖缺失的模块跳过，不误报
        pytest.skip(f"{mod_name} 导入失败: {type(e).__name__}: {e}")
    if not hasattr(mod, getter) or not hasattr(mod, var):
        pytest.skip(f"{mod_name} 缺 {getter}/{var}")

    ctor_name = _ctor_name(mod.__file__, var)
    calls = {"n": 0}
    lock = threading.Lock()
    if ctor_name and hasattr(mod, ctor_name):
        real = getattr(mod, ctor_name)

        class _Slow(real):  # type: ignore[misc,valid-type]
            def __init__(self, *a, **k):
                import time as _t

                _t.sleep(0.01)  # 放大竞态窗口
                with lock:
                    calls["n"] += 1
                super().__init__(*a, **k)

        _Slow.__name__ = ctor_name
        setattr(mod, ctor_name, _Slow)

    setattr(mod, var, None)  # 重置单例
    fn = getattr(mod, getter)
    results: list[object] = []
    barrier = threading.Barrier(16)

    def call():
        try:
            barrier.wait()
            results.append(fn())
        except Exception as e:  # noqa: BLE001
            results.append(("err", repr(e)[:80]))

    ts = [threading.Thread(target=call) for _ in range(16)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()

    ids = {id(r) for r in results if not isinstance(r, tuple)}
    assert len(results) == 16, f"{getter}: 返回数不足 16"
    assert len(ids) == 1, f"{getter}: 出现 {len(ids)} 个不同实例 → DCL 失效"
    if ctor_name:
        assert calls["n"] == 1, f"{getter}: 构造函数执行 {calls['n']} 次 > 1"


# ────────────────────────── C. 原子写入口 ──────────────────────────

class TestAtomicWriteJson:
    def test_writes_complete_file(self, tmp_path):
        from system.config import atomic_write_json

        target = tmp_path / "sub" / "config.json"
        atomic_write_json(target, {"a": 1, "中文": "值"})
        assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "中文": "值"}

    def test_failure_leaves_target_intact(self, tmp_path, monkeypatch):
        """序列化失败 → 目标文件保持原内容，且不残留 .tmp。"""
        import os

        from system.config import atomic_write_json

        target = tmp_path / "config.json"
        target.write_text('{"keep": true}', encoding="utf-8")

        class _Boom:
            def __repr__(self):  # json.dump 会调到这里
                raise RuntimeError("boom")

        with pytest.raises(Exception):
            atomic_write_json(target, {"bad": _Boom()})
        assert target.read_text(encoding="utf-8") == '{"keep": true}'
        leftovers = [p.name for p in os.listdir(tmp_path) if p.startswith(".config_")]
        assert leftovers == [], f"残留临时文件: {leftovers}"

    def test_concurrent_writes_never_produce_partial_file(self, tmp_path):
        """4 写 + 4 读持续 1s。

        硬断言：读者**永不**读到非法 JSON（这正是"原子"的定义）。
        容忍项：写者在极端句柄争抢下耗尽重试后**显式抛 OSError** ——
        这是函数契约（重试后抛出，不静默吞），失败必须可见而非产出半截文件。
        """
        from system.config import atomic_write_json

        target = tmp_path / "config.json"
        atomic_write_json(target, {"init": True})
        bad: list[str] = []
        writer_errors: list[str] = []
        writes_ok: list[int] = []
        stop = threading.Event()

        def writer(i: int):
            while not stop.is_set():
                try:
                    atomic_write_json(target, {"w": i, "pad": "x" * 2000})
                    writes_ok.append(1)
                except OSError as e:  # 争抢耗尽重试 → 显式失败（不产出半截文件）
                    writer_errors.append(repr(e)[:60])

        def reader():
            while not stop.is_set():
                try:
                    json.loads(target.read_text(encoding="utf-8"))
                except Exception as e:  # noqa: BLE001
                    bad.append(repr(e)[:80])

        ws = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        rs = [threading.Thread(target=reader) for _ in range(4)]
        for t in ws + rs:
            t.start()
        import time as _t

        _t.sleep(1.0)
        stop.set()
        for t in ws + rs:
            t.join()
        assert writes_ok, "一次成功写入都没有"
        assert bad == [], f"读到非法 JSON {len(bad)} 次: {bad[:3]}"
        assert len(writes_ok) > len(writer_errors), (
            f"写失败({len(writer_errors)})不应多于成功({len(writes_ok)}) —— 重试预算不足")
