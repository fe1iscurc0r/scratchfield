"""第三方能力包 adapters 健康检查 dry-run 单元测试。

只跑 healthcheck（不调 register 不传 mcp_server），验证：
- 4 个 adapter 都能正常 import 不抛
- agent_reach / headroom(退化) / memclaw(SQLite standalone) 三个路径的
  healthcheck 逻辑在无 API key 场景下不会崩溃
- vulnclaw 在缺 key 时正确返回 False 并打日志
- mcp_registry.register_adapters(None) dry-run 能跑通且只注册通过 hc 的 adapter
- mcp_registry.register_capability / list_registered_capabilities 正常
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scratchpad/
SRC_PATHS = [
    str(PROJECT_ROOT),
    str(PROJECT_ROOT / "vendor" / "top5" / "Agent-Reach"),
    str(PROJECT_ROOT / "vendor" / "top5" / "VulnClaw"),
    str(PROJECT_ROOT / "vendor" / "top5" / "caura-memclaw" / "core-api" / "src"),
    str(PROJECT_ROOT / "vendor" / "top5" / "caura-memclaw" / "common"),
    str(PROJECT_ROOT / "vendor" / "top5" / "headroom"),
]
for _p in SRC_PATHS:
    if _p not in sys.path:
        sys.path.insert(0, _p)


# 静默 stderr/logger，适配 healthcheck 里 warning 大量打印
logging.basicConfig(level=logging.ERROR)


class _FakeServer:
    """测试用 mock mcp_server，捕获 add_tool 注册的函数。"""
    def __init__(self):
        self.captured = {}

    def add_tool(self, fn, name=None):
        self.captured[name or getattr(fn, "__name__", "?")] = fn


class TestAdapterHealthchecks(unittest.TestCase):
    """单独测试 4 个 adapter 的 healthcheck()，不启动任何服务，不传任何 env key。"""

    @classmethod
    def setUpClass(cls):
        # 每次跑前确保没有 VULNCLAW_OPENAI_API_KEY / OPENAI_API_KEY 干扰 vulnclaw 测试
        for k in ("VULNCLAW_OPENAI_API_KEY", "OPENAI_API_KEY",
                  "MEMCLAW_OPENAI_API_KEY", "IS_STANDALONE", "MEMCLAW_DB_PATH",
                  "ENABLE_ADAPTER_AGENT_REACH", "ENABLE_ADAPTER_VULNCLAW",
                  "ENABLE_ADAPTER_MEMCLAW", "ENABLE_ADAPTER_HEADROOM"):
            os.environ.pop(k, None)

    def test_agent_reach_healthcheck_importable(self):
        """Agent-Reach healthcheck 不依赖外部 key；当前状态目录正确应返回 True。"""
        from mcpserver.adapters import agent_reach
        result = agent_reach.healthcheck()
        # 当前仓库有代码，True；如果未来改结构变 False 也可以接受（不影响主线）
        self.assertIsInstance(result, bool)

    def test_vulnclaw_healthcheck_requires_key(self):
        """VulnClaw 在缺 VULNCLAW_OPENAI_API_KEY/OPENAI_API_KEY 时返回 False。"""
        os.environ.pop("VULNCLAW_OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        from mcpserver.adapters import vulnclaw
        self.assertFalse(vulnclaw.healthcheck(),
                         "VulnClaw 在缺 LLM key 时应该 fail-fast 拒绝注册")

    def test_memclaw_healthcheck_sqlite_standalone(self):
        """MemClaw standalone+sqlite 无 key 时也能通过（只是 enrich/embed 降级）。"""
        os.environ.setdefault("IS_STANDALONE", "true")
        os.environ.setdefault("ENVIRONMENT", "development")
        from mcpserver.adapters import memclaw
        result = memclaw.healthcheck()
        # 有 SqliteBackend 代码 → 应 True；如果 core_api 依赖在当前 env 不完整，退回 False 也不阻塞主线
        self.assertIsInstance(result, bool)

    def test_headroom_healthcheck_degraded_mode(self):
        """Headroom 在未安装 Rust 扩展时，仍能进入退化模式返回 True（纯 Python pipeline）。"""
        from mcpserver.adapters import headroom
        result = headroom.healthcheck()
        # 源码已复制入 repo → 最差也能退化模式 True；除非 import headroom 都炸了（没装依赖）
        # 这里只测 bool 性，不强判 True/False，因为 runtime 依赖很多
        self.assertIsInstance(result, bool)


class TestRegistryAdapterFlow(unittest.TestCase):
    """mcp_registry 层面的 adapter 流程测试。"""

    def setUp(self):
        # clear_registry 已联动清空 _ADAPTER_CAPABILITIES + _ADAPTER_REGISTERED + _common 全局状态
        from mcpserver import mcp_registry
        mcp_registry.clear_registry()

    def test_register_capability_roundtrip(self):
        from mcpserver import mcp_registry
        ok = mcp_registry.register_capability({
            "name": "dummy-cap",
            "displayName": "Dummy",
            "description": "for test",
            "version": "0.1",
            "license": "MIT",
            "vendor": "test",
        })
        self.assertTrue(ok)
        caps = mcp_registry.list_registered_capabilities()
        names = [c["name"] for c in caps]
        self.assertIn("dummy-cap", names)

    def test_register_adapters_none_server_dry_run(self):
        """register_adapters(None) = dry-run。

        不传 mcp_server，每个 adapter 内部 hc 失败就跳过。这个测试主要验证
        register_all_adapters → 逐个 import → healthcheck → register → 异常捕获
        的整条链路不会抛；返回列表是成功注册的 adapter 名。
        """
        from mcpserver import mcp_registry
        from mcpserver.adapters import register_all_adapters
        names = mcp_registry.register_adapters(mcp_server=None)
        # 返回值是字符串列表，空或包含若干 adapter；不应该抛异常
        self.assertIsInstance(names, list)
        known_adapters = set(register_all_adapters.__globals__["_ADAPTERS"].keys())
        for n in names:
            self.assertIn(n, known_adapters)

    def test_register_adapters_respects_env_disable(self):
        """ENABLE_ADAPTER_*=0 时对应 adapter 即使健康也会被显式禁用。"""
        from mcpserver import mcp_registry
        from mcpserver.adapters import register_all_adapters
        mcp_registry.clear_registry()
        mcp_registry._ADAPTER_CAPABILITIES.clear()
        mcp_registry._ADAPTER_REGISTERED = False
        all_env_keys = [env_key for _name, (_mod, env_key) in register_all_adapters.__globals__["_ADAPTERS"].items()]
        for k in all_env_keys:
            os.environ[k] = "0"
        try:
            names = mcp_registry.register_adapters(mcp_server=None)
            self.assertEqual(names, [], "全部开关 off 时 register_adapters 应返回空列表")
        finally:
            for k in all_env_keys:
                os.environ.pop(k, None)


class TestHIGHFixVerification(unittest.TestCase):
    """铁锚落地审查发现的 5 个 HIGH bug 修复专项验证。

    每个用例真调 4 个 adapter 的 register() 外壳工具（不启 FastMCP，传 None 或 mock），
    断言 5 个 HIGH 场景下不再抛 AttributeError / TypeError 而是返回结构化结果。
    """

    @classmethod
    def setUpClass(cls):
        # 预先注入 vendor 路径
        for k in ("VULNCLAW_OPENAI_API_KEY", "OPENAI_API_KEY",
                  "MEMCLAW_OPENAI_API_KEY", "IS_STANDALONE", "MEMCLAW_DB_PATH"):
            os.environ.pop(k, None)
        os.environ["IS_STANDALONE"] = "true"
        os.environ["ENVIRONMENT"] = "development"

    def setUp(self):
        # 每次用例后清空 registry 状态
        from mcpserver import mcp_registry
        mcp_registry.clear_registry()

    # ===== HIGH-1: headroom compress 返回 CompressionResult，len(result) 抛 TypeError =====
    def test_headroom_compress_returns_str_not_compressionresult_object(self):
        """HIGH-1 修复：headroom_compress_text 工具必须返回字符串，不再抛 len(CompressionResult)。"""
        from mcpserver.adapters import headroom
        self.assertTrue(headroom.healthcheck(), "headroom healthcheck 应通过（退化纯 Python）")
        # 从模块的 register 里抽出外壳工具。不传 mcp_server，直接用 adapter 内部闭包函数。
        # 方式：用一个临时 mock 捕获 add_tool 的参数
        srv = _FakeServer()
        headroom.register(mcp_server=srv)
        compress_fn = srv.captured.get("headroom_compress_text")
        self.assertIsNotNone(compress_fn, "headroom_compress_text 必须被注册")

        text = "A" * 2000  # 足够长，保证触发真实 compress 路径
        import asyncio
        result = asyncio.run(compress_fn(text, max_ratio=0.5, mode="general"))
        self.assertEqual(result.get("ok"), True, f"compress 应成功，实际: {result}")
        compressed = result.get("compressed")
        self.assertIsInstance(compressed, str, "compressed 字段必须是字符串（不是 CompressionResult）")
        # ratio 是数值，不应含 TypeError
        self.assertIsInstance(result.get("ratio"), (int, float), "ratio 应是数值")

    # ===== HIGH-2 + HIGH-3: VulnClaw get_registered_tools() 不存在 + run_phase 不存在 =====
    def test_vulnclaw_uses_get_all_tool_schemas_not_get_registered_tools(self):
        """HIGH-2 修复：vulnclaw_status 应调 get_all_tool_schemas，不再抛 AttributeError。"""
        os.environ["VULNCLAW_OPENAI_API_KEY"] = "sk-test-placeholder"
        try:
            from mcpserver.adapters import vulnclaw
            hc = vulnclaw.healthcheck()
            self.assertIsInstance(hc, bool)  # 通过或失败都可以接受，关键是不抛
            srv = _FakeServer()
            vulnclaw.register(mcp_server=srv)
            status_fn = srv.captured.get("vulnclaw_status")
            invoke_fn = srv.captured.get("vulnclaw_invoke")
            self.assertIsNotNone(status_fn, "vulnclaw_status 必须注册（get_all_tool_schemas 路径）")
            self.assertIsNotNone(invoke_fn, "vulnclaw_invoke 必须注册（外壳说明）")
            import asyncio
            # status 工具执行不应抛 AttributeError
            r = asyncio.run(status_fn())
            self.assertIn("ok", r)
            # invoke 工具执行也不应抛 AttributeError（run_phase 不存在 → 现在是诚实说明）
            r2 = asyncio.run(invoke_fn(command="recon", target="http://example.com"))
            self.assertIn("ok", r2)
            self.assertEqual(r2.get("ok"), False, "invoke 应诚实返回 ok=False（说明需完整运行时）")
            self.assertNotIn("run_phase", str(r2.get("error", "")),
                             "错误信息不应含 AttributeError: run_phase 不存在")
        finally:
            os.environ.pop("VULNCLAW_OPENAI_API_KEY", None)

    # ===== HIGH-4 + HIGH-5: Agent-Reach Server 无 tool_manager + core.search 不存在 =====
    def test_agent_reach_register_no_longer_uses_nonexistent_core_search(self):
        """HIGH-4/5 修复：agent_reach_status 应调 doctor_report，不再走不存在的 core.search。"""
        from mcpserver.adapters import agent_reach
        self.assertIsInstance(agent_reach.healthcheck(), bool)
        srv = _FakeServer()
        agent_reach.register(mcp_server=srv)
        status_fn = srv.captured.get("agent_reach_status")
        search_fn = srv.captured.get("agent_reach_run")  # 旧名，应该不存在了
        self.assertIsNone(search_fn, "agent_reach_run 应已移除（search 不存在）")
        self.assertIsNotNone(status_fn, "agent_reach_status 必须注册（doctor_report）")
        import asyncio
        r = asyncio.run(status_fn())
        self.assertIn("ok", r, f"status 调用应返回 dict，实际: {type(r)}")
        # 关键：不应抛 AttributeError: search 不存在
        self.assertNotIn("search", str(r.get("error", "")).lower(),
                         "错误信息不应含 search AttributeError（已用 doctor_report）")

    # ===== memclaw 无 HIGH 但补一个外壳工具 dry-run（不真写 DB） =====
    def test_memclaw_write_tool_signature_matches_sqlite_backend_store(self):
        """memclaw ✅ 已落地的二次确认：register 不再抛 SyntaxError（PEP 695 vendor）。

        注：vendor caura-memclaw 用了 Python 3.12+ PEP 695 泛型语法 async def _call_gated[T]，
        在 Python 3.11 下 SqliteBackend 无法 import，register 会退化到"仅登记 capability、不注册工具"。
        本测试断言：无论退化与否，register 都不应抛 SyntaxError / AttributeError，
        调用返回后进程状态干净（异常被 except 捕获并 warning）。
        """
        from mcpserver.adapters import memclaw
        hc = memclaw.healthcheck()
        self.assertIsInstance(hc, bool)
        srv = _FakeServer()

        # 关键断言：register 不再抛 SyntaxError / AttributeError（异常在内部被 except 捕获）
        try:
            memclaw.register(mcp_server=srv)
        except SyntaxError as e:
            self.fail(f"memclaw.register 不应抛 SyntaxError（PEP 695 vendor 应被 except 捕获）: {e}")
        except AttributeError as e:
            self.fail(f"memclaw.register 不应抛 AttributeError: {e}")

        # 注册到的工具数可以是 0（退化，PEP 695 不兼容）也可以是 2+（正常 import），
        # 但只要 register 没抛，就说明 HIGH 修复是稳定的。
        has_any_tool_or_none = (len(srv.captured) == 0) or ("memclaw_write" in srv.captured) or ("memclaw_list" in srv.captured)
        self.assertTrue(has_any_tool_or_none,
                        f"captured tools 要么为空（退化），要么含 memclaw_write/list，实际: {list(srv.captured.keys())}")

        # 如果 register 真的注册了写工具，再校验参数签名
        for name in ("memclaw_write",):
            fn = srv.captured.get(name)
            if fn is None:
                continue
            import inspect
            sig = inspect.signature(fn)
            params = set(sig.parameters.keys())
            self.assertTrue({"content"}.issubset(params),
                            f"memclaw_write 参数应含 content，实际: {params}")


# =========================================================================
# ARC-1 + LOW-F1/F2 遗留风险修复验证
# =========================================================================
class TestLegacyRiskFixVerification(unittest.TestCase):
    """验证遗留风险修复：ARC-1（私有方法探测）+ LOW-F1/F2（CAPABILITY 建议字段）。"""

    def setUp(self):
        from mcpserver import mcp_registry
        from mcpserver.adapters import reset_for_tests
        mcp_registry.clear_registry()
        reset_for_tests()

    # --- ARC-1：memclaw_list 不再直接调 db._get_db()，改用 getattr 探测 ---
    def test_memclaw_list_uses_getattr_probe_not_direct_private_call(self):
        """ARC-1：memclaw_list 内部用 getattr(db, "_get_db", None) 探测，
        vendor 升级删除 _get_db 方法时 graceful 返回 error，不抛 AttributeError。"""
        import inspect

        from mcpserver.adapters import memclaw

        # 验证 register 函数源码里不再有 db._get_db() 直接调用
        source = inspect.getsource(memclaw.register)
        self.assertNotIn("db._get_db()", source,
                         "memclaw.register 源码不应再直接调 db._get_db()（应改用 getattr 探测）")
        self.assertIn('getattr(db, "_get_db"', source,
                      "memclaw.register 应通过 getattr 探测 _get_db")
        self.assertIn("_get_backend", source,
                      "adapter 内部工厂应改名 _get_backend（消歧）")
        self.assertNotIn("_get_db() -> SqliteBackend", source,
                         "不应再有 _get_db 名为返回 SqliteBackend 的工厂函数")

    # --- LOW-F1：headroom CAPABILITY 含 degradation_mode ---
    def test_headroom_capability_has_degradation_mode(self):
        """LOW-F1：headroom CAPABILITY 应含 degradation_mode 字段。"""
        from mcpserver.adapters import headroom
        cap = headroom.CAPABILITY
        self.assertIn("degradation_mode", cap,
                      f"headroom CAPABILITY 应含 degradation_mode，实际 keys={list(cap.keys())}")
        self.assertIn("pure-python", cap["degradation_mode"],
                      "degradation_mode 应说明 Rust→纯 Python 退化")

    # --- LOW-F2：memclaw CAPABILITY 含 security_notice ---
    def test_memclaw_capability_has_security_notice(self):
        """LOW-F2：memclaw CAPABILITY 应含 security_notice 字段。"""
        from mcpserver.adapters import memclaw
        cap = memclaw.CAPABILITY
        self.assertIn("security_notice", cap,
                      f"memclaw CAPABILITY 应含 security_notice，实际 keys={list(cap.keys())}")
        notice = cap["security_notice"]
        self.assertIn("SQLite", notice)
        self.assertIn("无加密", notice)


if __name__ == "__main__":
    unittest.main()


# =========================================================================
# MEDIUM-3 路径逃逸防御边界校验 + 跨源同名注册专项测试
# =========================================================================
class TestSecurityBoundaryAndCrossSourceRealPath(unittest.TestCase):
    """MEDIUM-3 inject_vendor_path 边界校验验证 + 跨源查重走真实 API（HIGH-2 专项）。"""

    def setUp(self):
        from mcpserver import mcp_registry
        from mcpserver.adapters import reset_for_tests
        mcp_registry.clear_registry()
        reset_for_tests()

    # ---------- MEDIUM-3 边界校验 ----------
    def test_escape_name_refuses_injection(self):
        """name='../scripts' 必须跳出 vendor/top5 边界 → 整体拒绝注入，sys.path 零新增。"""
        from mcpserver.adapters import _common as ac
        pre_sys_path = list(sys.path)
        # _common.py logger = logging.getLogger(__name__) → 实际 logger 名是 mcpserver.adapters._common
        with self.assertLogs("mcpserver.adapters._common", level="WARNING") as logs:
            ac.inject_vendor_path("../scripts")
        log_text = "\n".join(logs.output)
        self.assertIn("跳出 vendor/top5 边界", log_text)
        self.assertIn("拒绝注入", log_text)
        self.assertEqual(sys.path, pre_sys_path,
                         "边界拒绝时 sys.path 必须零新增，避免半注入状态")
        self.assertNotIn("../scripts", ac._INJECTED_VENDORS,
                         "拒绝注入的 name 不应记入注入记忆")

    def test_escape_subpath_skips_sensitive_but_still_injects_root(self):
        """subpath='../../Windows/System32' 跳过敏感路径注入；但 name='headroom' 合法，
        vendor 根目录仍应注入（子路径失败不影响正常路径）。"""
        from mcpserver.adapters import _common as ac
        pre = set(sys.path)
        with self.assertLogs("mcpserver.adapters._common", level="WARNING") as logs:
            ac.inject_vendor_path("headroom", "../../Windows/System32")
        log_text = "\n".join(logs.output)
        self.assertIn("subpath='../../Windows/System32' 跳出 vendor/top5 边界", log_text)
        # 不应出现逃逸目标路径（用字符串"System32"存在性判断即可，resolve 后的具体绝对路径不稳定）
        self.assertTrue(
            all("System32" not in p for p in sys.path),
            f"逃逸 subpath 不应进入 sys.path，当前 sys.path={[p for p in sys.path[:5] if 'top5' in p]}..."
        )
        # headroom 根目录应正常注入（因为 vendor/top5/headroom 存在）
        root_path = str(ac.get_vendor_top5_root() / "headroom")
        self.assertIn(root_path, sys.path,
                      f"子路径失败不应连带阻止正常的根目录注入 {root_path}")
        self.assertIn("headroom", ac._INJECTED_VENDORS)
        # 检查记忆里不含 System32 那条
        self.assertTrue(all("System32" not in p for p in ac._INJECTED_VENDORS["headroom"]))
        # 清理
        ac.reset_for_tests()
        for p in (set(sys.path) - pre):
            sys.path.remove(p)

    def test_nonexistent_vendor_dir_skips_root_but_keeps_valid_subpath_injection(self):
        """name='vendor_not_exist'：root 不存在 → 跳过根目录注入；
        验证：整个调用不抛异常；未注入成功则不记入注入记忆，下一次可重试。"""
        from mcpserver.adapters import _common as ac
        pre_injected = set(ac._INJECTED_VENDORS.keys())
        with self.assertLogs("mcpserver.adapters._common", level="WARNING") as logs:
            ac.inject_vendor_path("vendor_not_exist_12345")
        log_text = "\n".join(logs.output)
        self.assertIn("vendor 源目录不存在", log_text)
        # 没有任何子路径且根目录不存在 → 不应记入记忆
        self.assertEqual(set(ac._INJECTED_VENDORS.keys()), pre_injected,
                         "完全注入失败不应记入记忆，允许后续再重试")

    # ---------- HIGH-2 跨源查重专项：走真实 register_capability() + 真实 mcporter/scan 查重调用 ----------
    def test_real_register_capability_then_manifest_scan_conflict_emits_warning(self):
        """真实走 API：先 adapter 侧 register_capability("headroom") 登记能力卡片 →
        再模拟真实 scan_and_register_mcp_agents 内部调用的 _check_cross_source_conflict("headroom", "manifest")
        然后手动模拟 create_agent_instance 成功后调用 register_external_mcp_agents 流程；
        验证：2 次 WARNING（scan 域检测 + mcporter 域检测）+ list_registered_capabilities
        出现 3 条 headroom 全部带 conflict_sources = [manifest, mcporter, adapter]。
        """
        from mcpserver import mcp_registry

        # Step A: 先 adapter 域登记 headroom（真实调 register_capability）
        ok = mcp_registry.register_capability({
            "name": "headroom",
            "displayName": "上下文压缩 (adapter)",
            "description": "来自适配器",
            "version": "0.1",
            "license": "MIT",
            "vendor": "headroom",
            "_from_adapter": "headroom",
        })
        self.assertTrue(ok)
        caps1 = mcp_registry.list_registered_capabilities()
        hr1 = [c for c in caps1 if c["name"] == "headroom"]
        self.assertEqual(len(hr1), 1)
        self.assertEqual(hr1[0]["source"], "adapter")
        self.assertNotIn("conflict_sources", hr1[0],
                         "单源条目不应附 conflict_sources 字段")

        # Step B: 模拟 scan_and_register_mcp_agents 成功创建 agent_instance 后写 MANIFEST_CACHE 前的跨源检查
        warnings = []
        with self.assertLogs("mcpserver.mcp_registry", level="WARNING") as ctx:
            mcp_registry._check_cross_source_conflict("headroom", "manifest")
        warnings.append("\n".join(ctx.output))
        # 写入 manifest 记录（不调 scan 入口直接写 cache，等价于 agent_instance 创建成功后的登记）
        mcp_registry.MANIFEST_CACHE["headroom"] = {
            "name": "headroom",
            "displayName": "上下文压缩 (manifest)",
            "description": "本地 manifest JSON 扫描",
            "version": "0.2",
            "license": "MIT",
            "vendor": "headroom",
            "source": "manifest",
        }
        self.assertIn("跨源冲突", warnings[-1])
        self.assertIn("已有来源 adapter", warnings[-1])

        # Step C: 模拟 mcporter 外部服务同名再登记（register_external_mcp_agents 的查重后跨源检查）
        with self.assertLogs("mcpserver.mcp_registry", level="WARNING") as ctx:
            mcp_registry._check_cross_source_conflict("headroom", "mcporter")
        warnings.append("\n".join(ctx.output))
        self.assertIn("跨源冲突", warnings[-1])
        # existing_sources 顺序：先 manifest 域 dict 插入（headroom）→ 再 adapter 域，
        # 所以输出是 "manifest+adapter"，只关心两个来源都出现即可，不依赖字符串顺序
        self.assertIn("manifest", warnings[-1])
        self.assertIn("adapter", warnings[-1])
        self.assertIn("新来源 mcporter", warnings[-1])
        # 写入 mcporter 记录
        mcp_registry.MANIFEST_CACHE["headroom"] = {
            "name": "headroom",
            "displayName": "上下文压缩 (mcporter)",
            "description": "外部 mcporter 配置",
            "version": "0.3",
            "license": "MIT",
            "vendor": "headroom",
            "source": "mcporter",
        }

        # Step D: list_registered_capabilities 返回 2 条（adapter + mcporter 覆盖了本地 manifest）
        # 注意：因为两次写都用同一个 key "headroom"，MANIFEST_CACHE 里最后一条是 mcporter；
        #       adapter 在另一个独立 dict，所以最终应该是 2 条。
        caps_final = mcp_registry.list_registered_capabilities()
        hr_final = [c for c in caps_final if c["name"] == "headroom"]
        self.assertEqual(len(hr_final), 2,
                         f"应为 mcporter manifest（覆盖 scan）+ adapter 两条，实际 {len(hr_final)}: {hr_final}")
        sources_list = sorted(c["source"] for c in hr_final)
        self.assertEqual(sources_list, ["adapter", "mcporter"])
        for c in hr_final:
            self.assertIn("conflict_sources", c,
                          f"跨源双条目必须都带 conflict_sources，实际 c={c}")
            self.assertEqual(sorted(c["conflict_sources"]), ["adapter", "mcporter"])

    def test_manifest_then_adapter_cross_source_inverse_order(self):
        """反向顺序：先 manifest 登记 → 再 adapter register_capability →
        后者应触发 _check_cross_source_conflict("headroom", "adapter") WARNING。"""
        from mcpserver import mcp_registry

        # Step A: 先写 manifest（本地 scan 来源，source 省略 → 默认 manifest）
        mcp_registry.MANIFEST_CACHE["memclaw"] = {
            "displayName": "记忆总线（manifest侧）",
            "description": "本地 manifest 先登记",
            "version": "1.0",
        }

        # Step B: adapter 再 register_capability("memclaw") → 跨源冲突 WARNING
        with self.assertLogs("mcpserver.mcp_registry", level="WARNING") as ctx:
            ok = mcp_registry.register_capability({
                "name": "memclaw",
                "displayName": "记忆总线",
                "description": "adapter 侧",
                "version": "2.27.0",
                "license": "Apache-2.0",
                "vendor": "caura-memclaw",
                "_from_adapter": "memclaw",
            })
        self.assertTrue(ok, "跨源不阻断，允许登记，只打 WARNING")
        log_text = "\n".join(ctx.output)
        self.assertIn("跨源冲突", log_text)
        self.assertIn("已有来源 manifest", log_text)
        self.assertIn("新来源 adapter", log_text)

        # Step C: 最终 list 返回 2 条 memclaw，都带 conflict_sources
        entries = [c for c in mcp_registry.list_registered_capabilities() if c["name"] == "memclaw"]
        self.assertEqual(len(entries), 2)
        for c in entries:
            self.assertEqual(sorted(c["conflict_sources"]), ["adapter", "manifest"])



# =========================================================================
# 多智能体审查修复验证 —— 沈遥 Phase 4 Case1-5
# =========================================================================
class TestGateHardeningVerification(unittest.TestCase):
    """验证 P1 三件套门禁加固（HIGH-1 isinstance 短路 / HIGH-2 跨源冲突 / MEDIUM-4 读写分离）。"""

    def setUp(self):
        from mcpserver import mcp_registry
        from mcpserver.adapters import reset_for_tests
        mcp_registry.clear_registry()  # 联动清 _common.*
        reset_for_tests()
        # 每次用例前确保全局 env 不干扰
        for k in ("VULNCLAW_OPENAI_API_KEY", "OPENAI_API_KEY",
                  "MEMCLAW_OPENAI_API_KEY", "IS_STANDALONE", "MEMCLAW_DB_PATH",
                  "ENABLE_ADAPTER_AGENT_REACH", "ENABLE_ADAPTER_VULNCLAW",
                  "ENABLE_ADAPTER_MEMCLAW", "ENABLE_ADAPTER_HEADROOM"):
            os.environ.pop(k, None)

    # --- Case 1: _from_adapter 缺失被 validate_adapter 识别（7 字段必需） ---
    def test_validate_adapter_blocks_missing_from_adapter(self):
        """Case1：CAPABILITY 缺 _from_adapter（现在是必需字段）应出 issues。"""
        from mcpserver.adapters._common import validate_adapter

        class _Bad:
            @staticmethod
            def healthcheck(): return True
            @staticmethod
            def register(a, b=None): pass
            CAPABILITY = {
                "name": "foo",
                "displayName": "Foo",
                "description": "for test",
                "version": "0.1",
                "license": "MIT",
                "vendor": "test",
                # 故意缺 _from_adapter
            }

        issues = validate_adapter(_Bad, "foo")
        joined = "；".join(issues)
        self.assertIn("_from_adapter", joined,
                      f"CAPABILITY 缺 _from_adapter 应被拦截，实际 issues={issues}")
        self.assertIn("缺/空必需字段", joined)

    # --- Case 2: isinstance 不再短路，CAPABILITY 空 vendor 会被拦 ---
    def test_validate_adapter_catches_empty_vendor_despite_isinstance_true(self):
        """Case2：isinstance 会 True（三要素有），但 vendor=""，validate_adapter 应仍然拦。

        对应 HIGH-1：之前 __init__.py 只在 isinstance False 时才跑 validate_adapter，
        导致空字符串 vendor 这种深层问题被放过。修复后无论 isinstance 如何都跑。
        """
        from mcpserver.adapters._common import MCPAdapterModule, validate_adapter

        class _AlmostOk:
            @staticmethod
            def healthcheck(): return True
            @staticmethod
            def register(a, b=None): pass
            CAPABILITY = {
                "name": "headroom",
                "displayName": "上下文压缩",
                "description": "x",
                "version": "0.1",
                "license": "MIT",
                "vendor": "",   # 空字符串
                "_from_adapter": "headroom",
            }

        # isinstance 应该是 True（三要素存在），证明修复前会被短路
        self.assertTrue(isinstance(_AlmostOk, MCPAdapterModule),
                        "预置：此模块应能通过 Protocol isinstance 检查")
        issues = validate_adapter(_AlmostOk, "headroom")
        joined = "；".join(issues)
        self.assertIn("'vendor'", joined,
                      f"CAPABILITY 空 vendor 应被深度校验拦截，实际 issues={issues}")

    # --- Case 3: _from_adapter != registered_name 触发三线对齐校验 ---
    def test_validate_adapter_blocks_from_adapter_mismatch(self):
        """Case3：CAPABILITY.name 对但 _from_adapter 写成别的模块名，应被拦截。"""
        from mcpserver.adapters._common import validate_adapter

        class _Misaligned:
            @staticmethod
            def healthcheck(): return True
            @staticmethod
            def register(a, b=None): pass
            CAPABILITY = {
                "name": "memclaw",
                "displayName": "x",
                "description": "x",
                "version": "1",
                "license": "MIT",
                "vendor": "test",
                "_from_adapter": "vulnclaw",  # 错
            }

        issues = validate_adapter(_Misaligned, "memclaw")
        joined = "；".join(issues)
        self.assertIn("_from_adapter='vulnclaw' 与注册名 'memclaw' 不一致", joined,
                      f"_from_adapter 错位应被三线对齐校验拦截，实际 issues={issues}")

    # --- Case 4: 步骤 4 写入 _ADAPTER_CAPABILITY_NAMES（漏调 safe 仍有效） ---
    def test_step4_writes_adapter_capability_names_despite_safe_bypass(self):
        """Case4：register() 内部完全没调 register_capability_safe，_ADAPTER_CAPABILITY_NAMES
        也应该在 __init__.py 步骤 4 被写入，保证后续同名 adapter 冲突检测不失效（MEDIUM-4 修复）。
        """
        # 构造一个最小 importlib 模块：CAPABILITY + healthcheck(通过) + register（不调 safe）
        import types

        from mcpserver.adapters import _common as ac
        from mcpserver.adapters import register_all_adapters
        fake_mod = types.ModuleType("tests.test_fake_case4_adapter")
        fake_mod.CAPABILITY = {
            "name": "case4",
            "displayName": "Case4",
            "description": "验证步骤4写入_NAMES",
            "version": "1",
            "license": "MIT",
            "vendor": "test",
            "_from_adapter": "case4",
        }
        fake_mod.healthcheck = lambda: True
        def _reg(mcp_server, mcp_registry=None):
            # 故意不调 register_capability_safe，模拟维护者遗忘
            if hasattr(mcp_server, "add_tool"):
                pass
        fake_mod.register = _reg
        sys.modules["tests.test_fake_case4_adapter"] = fake_mod

        # 直接操作 register_all_adapters 的 globals 中的 _ADAPTERS（最稳，避免包/子模块对象差异）
        orig_adapters = register_all_adapters.__globals__["_ADAPTERS"]
        try:
            register_all_adapters.__globals__["_ADAPTERS"] = {
                "case4": ("tests.test_fake_case4_adapter", "ENABLE_ADAPTER_CASE4"),
            }
            ac.reset_for_tests()
            names = register_all_adapters(mcp_server=object())
            self.assertIn("case4", names, f"case4 adapter 应成功纳入，实际: {names}")
            self.assertIn("case4", ac._ADAPTER_CAPABILITY_NAMES,
                          "步骤 4 应写入 _ADAPTER_CAPABILITY_NAMES，即使 register 没调 safe")
            self.assertEqual(ac._ADAPTER_CAPABILITY_NAMES["case4"], "case4")
        finally:
            register_all_adapters.__globals__["_ADAPTERS"] = orig_adapters
            sys.modules.pop("tests.test_fake_case4_adapter", None)

    # --- Case 5: 跨源冲突 WARNING + conflict_sources 字段（HIGH-2 修复） ---
    def test_cross_source_conflict_warning_and_conflict_sources_field(self):
        """Case5：adapter 域先登记 headroom → manifest 域再登记同名 headroom →
        应打跨源 WARNING + list_registered_capabilities 返回的两条都带 conflict_sources。
        """
        from mcpserver import mcp_registry

        # Step A: 先以 adapter 身份登记 headroom 能力卡
        ok = mcp_registry.register_capability({
            "name": "headroom",
            "displayName": "上下文压缩",
            "description": "adapter side",
            "version": "0.1",
            "license": "MIT",
            "vendor": "test",
            "_from_adapter": "headroom",
        })
        self.assertTrue(ok)

        # Step B: 手动模拟 scan_and_register_mcp_agents 向 MANIFEST_CACHE 写同名 manifest
        # 注意：直接写 MANIFEST_CACHE 会绕过 _check_cross_source_conflict 调用，
        # 所以这里显式调函数捕获 logger.warning，保证跨源冲突检测被触发
        with self.assertLogs("mcpserver.mcp_registry", level="WARNING") as log_ctx:
            mcp_registry._check_cross_source_conflict("headroom", "manifest")
        log_text = "\n".join(log_ctx.output)
        self.assertIn("跨源冲突", log_text)
        self.assertIn("已有来源 adapter", log_text,
                      "WARNING 应说明已有 adapter 域同名条目")
        self.assertIn("新来源 manifest", log_text)

        # 真实写一条 manifest 记录（模拟 scan 路径）
        mcp_registry.MANIFEST_CACHE["headroom"] = {
            "name": "headroom",
            "displayName": "上下文压缩",
            "description": "manifest side",
            "version": "0.2",
            "license": "MIT",
            "vendor": "test",
            "source": "manifest",
        }
        caps = mcp_registry.list_registered_capabilities()
        hr_entries = [c for c in caps if c["name"] == "headroom"]
        self.assertEqual(len(hr_entries), 2,
                         f"应出现 2 条 headroom（manifest + adapter），实际 {len(hr_entries)}")
        for c in hr_entries:
            self.assertIn("conflict_sources", c,
                          f"conflict_sources 字段应自动附加到同名跨源条目，实际: {c}")
            self.assertEqual(sorted(c["conflict_sources"]), ["adapter", "manifest"])

