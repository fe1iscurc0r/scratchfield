import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
# -*- coding: utf-8 -*-
"""卷131 测试：HIL 评估器 / loop 快照 / 知识驱动 / 设备状态 + 体验验收场景。

运行：cd <repo> && python tests/test_w131.py -v
覆盖工单验收点：
- W131-02: 读=auto_approve、写=need_confirm、dangerous=block、热重载、偏好学习
- W131-03: save/load/clear、kill 模拟崩溃后 resume、敏感信息不落盘
- W131-04/07: query_relevant 相关返回、tag 后 recommendation 差异化、时间衰减
- W131-05: get_state 指标、心跳超时 offline、state_changed 事件
- W131-01: 体验场景 A（工具自修复闭环）/B（可逆自动不可逆确认）/C（rag 引用）
"""
import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------- W131-02: HILEvaluator ----------------

class TestHILEvaluator(unittest.TestCase):
    def _eval(self, tmp):
        from apiserver.hil_evaluator import HILEvaluator
        return HILEvaluator(prefs_path=Path(tmp) / "prefs.json")

    def test_read_auto_write_confirm_dangerous_block(self):
        with TemporaryDirectory() as tmp:
            h = self._eval(tmp)
            # 读 → auto_approve
            d = h.eval_action("file_read", {"path": "a.txt"})
            self.assertEqual(d.action, "auto_approve", d.reason)
            # 写（无偏好）→ need_confirm
            d = h.eval_action("file_write", {"path": "a.txt"})
            self.assertEqual(d.action, "need_confirm", d.reason)
            # dangerous 黑名单 → block
            h._rules["dangerous_tools"] = ["format_disk"]
            d = h.eval_action("format_disk", {})
            self.assertEqual(d.action, "block")
            # critical → 永远 need_confirm（即使读偏好）
            h._rules["critical_tools"] = ["send_email"]
            d = h.eval_action("send_email", {})
            self.assertEqual(d.action, "need_confirm")

    def test_manifest_dangerous_tag_blocks(self):
        with TemporaryDirectory() as tmp:
            h = self._eval(tmp)
            d = h.eval_action("custom_tool", {}, context={
                "tool_manifests": {"custom_tool": {"tags": ["dangerous"]}}})
            self.assertEqual(d.action, "block")

    def test_user_preference_learning(self):
        with TemporaryDirectory() as tmp:
            h = self._eval(tmp)
            d0 = h.eval_action("file_write", {"path": "a.txt"})
            self.assertEqual(d0.action, "need_confirm")
            h.record_user_response("file_write", {"path": "a.txt"}, confirmed=True)
            d1 = h.eval_action("file_write", {"path": "a.txt"})
            self.assertEqual(d1.action, "auto_approve",
                             f"同类操作确认过后应转 auto：{d1.reason}")

    def test_hot_reload(self):
        with TemporaryDirectory() as tmp:
            from apiserver.hil_evaluator import HILEvaluator
            rp = Path(tmp) / "rules.json"
            h = HILEvaluator(rules_path=rp, prefs_path=Path(tmp) / "p.json")
            self.assertEqual(h.eval_action("file_write", {}).action, "need_confirm")
            # 写新规则：把 auto 阈值调到 100（全都需要确认）
            rules = json.loads(rp.read_text()) if rp.exists() else {}
            rules["thresholds"] = {"auto_approve": 100, "block": -4.0}
            rp.write_text(json.dumps(rules))
            time.sleep(0.05)
            h.reload_if_changed()
            self.assertEqual(h.eval_action("file_read", {}).action, "need_confirm",
                             "规则热重载后行为应改变")


# ---------------- W131-03: LoopCheckpoint ----------------

class TestLoopCheckpoint(unittest.TestCase):
    def _cp(self, tmp):
        from apiserver.loop_checkpoint import LoopCheckpoint
        return LoopCheckpoint(store_dir=Path(tmp) / "cps")

    def test_save_load_clear_roundtrip(self):
        with TemporaryDirectory() as tmp:
            cp = self._cp(tmp)
            msgs = [{"role": "user", "content": "修复编译错误"},
                    {"role": "assistant", "content": "已执行 file_edit"}]
            cp.save("sess-1", msgs, round_num=3, tool_results=[
                {"tool": "file_edit", "ok": True, "brief": "saved"}])
            st = cp.load("sess-1")
            self.assertIsNotNone(st)
            self.assertEqual(st.round_num, 3)
            self.assertEqual(len(st.messages_summary), 2)
            self.assertEqual(st.tool_results_digest[0]["tool"], "file_edit")
            # kill 模拟：再 save 两轮后 load 取最新
            cp.save("sess-1", msgs, round_num=4)
            cp.save("sess-1", msgs, round_num=5)
            self.assertEqual(cp.load("sess-1").round_num, 5)
            # clear 后无快照
            cp.clear("sess-1")
            self.assertIsNone(cp.load("sess-1"))

    def test_sensitive_data_redacted(self):
        with TemporaryDirectory() as tmp:
            cp = self._cp(tmp)
            msgs = [{"role": "user",
                     "content": "用 api_key=sk-1234567890abcdef 调用",
                     "authorization": "Bearer xyz"}]
            cp.save("sess-sec", msgs, round_num=1)
            raw = (Path(tmp) / "cps" / "sess-sec.jsonl").read_text(encoding="utf-8")
            self.assertNotIn("sk-1234567890abcdef", raw, "密钥不得落盘")
            self.assertNotIn("Bearer xyz", raw, "凭证不得落盘")
            self.assertIn("[REDACTED]", raw)

    def test_resume_semantics(self):
        """崩溃（无 clear）后 load 仍在——resume 可用；正常结束（clear）后 load 空。"""
        with TemporaryDirectory() as tmp:
            cp = self._cp(tmp)
            cp.save("s", [{"role": "user", "content": "x"}], round_num=2)
            # 崩溃模拟：不 clear 直接 load
            self.assertTrue(cp.has_checkpoint("s"))
            # 正常结束
            cp.clear("s")
            self.assertFalse(cp.has_checkpoint("s"))


# ---------------- W131-04/07: KnowledgeDriver ----------------

class TestKnowledgeDriver(unittest.TestCase):
    def _kd(self, tmp):
        from apiserver.knowledge_driver import KnowledgeDriver
        kd = KnowledgeDriver(db_path=Path(tmp) / "kd.db")
        # Windows 句柄纪律：测试结束关连接，TemporaryDirectory 才能清理
        self.addCleanup(kd.close)
        return kd

    def test_ingest_and_query_relevant(self):
        with TemporaryDirectory() as tmp:
            kd = self._kd(tmp)
            try:
                kd.ingest("daily_brief", "木质素实验进展",
                          "木质素 NPs 水凝胶在 pH=7 下溶胀率 340%", tags=["lignin", "hydrogel"])
                kd.ingest("paper_digest", "蒸发论文",
                          "interfacial solar evaporation 效率创新高", tags=["solar"])
                # 相关检索
                hits = kd.query_relevant("木质素 水凝胶 溶胀实验设计", k=5)
                self.assertTrue(any("木质素" in h.title for h in hits),
                                "query_relevant 应返回相关项")
                self.assertEqual(hits[0].last_used_task, "木质素 水凝胶 溶胀实验设计"[:80])
                # 无关检索不误报
                empty = kd.query_relevant("quantum computing 量子计算", k=5)
                self.assertEqual(len(empty), 0)
            finally:
                kd.close()

    def test_tool_recommendation_differential(self):
        """成功工具排在失败工具前（差异化推荐）+ 时间衰减方向正确。"""
        with TemporaryDirectory() as tmp:
            kd = self._kd(tmp)
            try:
                # search 连续成功
                for _ in range(5):
                    kd.tag_tool_outcome("search", {"ok": True}, task_context="文献检索")
                # exec 连续失败
                for _ in range(5):
                    kd.tag_tool_outcome("exec", {"ok": False, "error": "RuntimeError"},
                                        task_context="文献检索")
                recs = kd.get_tool_recommendation("文献检索")
                self.assertTrue(recs, "应有推荐")
                names = [r.tool_name for r in recs]
                self.assertIn("search", names)
                self.assertIn("exec", names)
                self.assertLess(names.index("search"), names.index("exec"),
                                "成功工具应在失败工具之前（分数高）")
                # 效果差但不下线：exec 仍出现在推荐列表（可用）
                # 时间衰减：exec 后来成功一次 → 分数应回升
                s_before = next(r.score for r in kd.get_tool_recommendation("文献检索")
                                if r.tool_name == "exec")
                kd.tag_tool_outcome("exec", {"ok": True}, task_context="文献检索")
                s_after = next(r.score for r in kd.get_tool_recommendation("文献检索")
                               if r.tool_name == "exec")
                self.assertGreater(s_after, s_before, "0.7*old+0.3*1.0 应使失败分数回升")
            finally:
                kd.close()


# ---------------- W131-05: DeviceStateStore ----------------

class TestDeviceStateStore(unittest.TestCase):
    def test_register_update_get(self):
        from apiserver.device_state import DeviceStateStore
        store = DeviceStateStore()
        store.register("ic705")
        store.update_state("ic705", {"freq_hz": 7050000, "mode": "USB", "s_unit": 7})
        st = store.get_state("ic705")
        self.assertTrue(st.online)
        self.assertEqual(st.key_metrics["freq_hz"], 7050000)
        snap = store.perception_snapshot()
        self.assertIn("ic705", snap["device_online"])

    def test_heartbeat_timeout_offline(self):
        from apiserver.device_state import DeviceStateStore
        store = DeviceStateStore(heartbeat_timeout=0.05)
        store.register("gps")
        store.update_state("gps", {"sats": 8})
        self.assertTrue(store.get_state("gps").online)
        time.sleep(0.1)
        st = store.get_state("gps")
        self.assertFalse(st.online)
        self.assertEqual(st.offline_reason, "heartbeat_timeout")

    def test_state_changed_event(self):
        from apiserver.device_state import DeviceStateStore
        from apiserver.event_bus import Topics, get_bus
        bus = get_bus()
        received = []
        d = bus.on(Topics.DEVICE_STATE_CHANGED, lambda e: received.append(e))
        try:
            store = DeviceStateStore()
            store.update_state("esp32", {"rssi": -60})   # offline→online
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0]["device"], "esp32")
            self.assertEqual(received[0]["change"], "online")
        finally:
            d()  # 热拔插消费者不崩总线


# ---------------- W131-01: 体验验收场景 ----------------

class TestExperienceScenarios(unittest.TestCase):
    """场景化验收（不是单元测试）——失败即停的断言。"""

    def test_scenario_a_self_fix_loop(self):
        """场景 A：tool → 编辑失败 → 理解错误 → 自修复 → 成功。

        用 KnowledgeDriver + mock 工具序列模拟完整反馈闭环。
        """
        from apiserver.knowledge_driver import KnowledgeDriver
        with TemporaryDirectory() as tmp:
            kd = KnowledgeDriver(db_path=Path(tmp) / "a.db")
            try:
                # 第一次：file_edit 失败（语法错误）
                kd.tag_tool_outcome("file_edit", {"ok": False, "error": "SyntaxError"},
                                    task_context="代码修复")
                # 自修复轮：读错误 → 再编辑 → 成功
                kd.tag_tool_outcome("file_read", {"ok": True}, task_context="代码修复")
                kd.tag_tool_outcome("file_edit", {"ok": True}, task_context="代码修复")
                # 断言闭环成立：最终编辑成功且知识库记录了失败→成功的轨迹
                recs = kd.get_tool_recommendation("代码修复")
                edit_score = next(r.score for r in recs if r.tool_name == "file_edit")
                self.assertGreater(edit_score, 0.4, "一次成功应把 edit 分数拉过中值")
                stats = kd.stats()
                self.assertEqual(stats["tool_scores"], 2)
            finally:
                kd.close()

    def test_scenario_b_reversibility_gate(self):
        """场景 B：可逆（读/查）自动执行；不可逆（写/删）等待确认。"""
        from apiserver.hil_evaluator import HILEvaluator
        with TemporaryDirectory() as tmp:
            h = HILEvaluator(prefs_path=Path(tmp) / "b.json")
            reversible = [h.eval_action(t, {}) for t in ("file_read", "search", "query")]
            irreversible = [h.eval_action(t, {"path": "x"}) for t in ("file_write", "delete", "exec")]
            self.assertTrue(all(d.action == "auto_approve" for d in reversible),
                            "可逆操作应全部自动执行")
            self.assertTrue(all(d.action == "need_confirm" for d in irreversible),
                            "不可逆操作应全部等待确认")

    def test_scenario_c_knowledge_referenced(self):
        """场景 C：daily_brief 摄取后，对话检索命中知识（rag 非空）。"""
        from apiserver.knowledge_driver import KnowledgeDriver
        with TemporaryDirectory() as tmp:
            kd = KnowledgeDriver(db_path=Path(tmp) / "c.db")
            try:
                # 模拟 cron 摄取今日简报（W131-04.4 管道）
                kd.ingest("daily_brief", "今日简报",
                          "TGA 数据管道完成校准，木质素热解动力学参数已入库", tags=["daily"])
                # 对话开始：loop 检索（等价 rag_section 注入逻辑）
                items = kd.query_relevant("热解动力学 参数从哪来", k=3)
                self.assertTrue(items, "rag_section 应非空（简报被引用）")
                self.assertIn("木质素", items[0].content)
            finally:
                kd.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
