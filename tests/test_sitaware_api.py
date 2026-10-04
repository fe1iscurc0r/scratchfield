# -*- coding: utf-8 -*-
"""卷132 sitaware 后端 API 回归测试（unittest 风格，TestClient + 临时 DB，离线）。

三种跑法：
    python tests/test_sitaware_api.py            # 直接跑，结果落 wb_unittest_result.txt
    python -m unittest tests.test_sitaware_api -v
    pytest tests/test_sitaware_api.py -q         # 仓库环境 pytest 可用时
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import os
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient

_DB = os.path.join(tempfile.gettempdir(),
                   f"sitaware_test_api_{os.getpid()}.db")  # 每次运行唯一名，避免文件锁竞争


class SitawareAPITest(unittest.TestCase):
    client: TestClient = None  # type: ignore

    @classmethod
    def setUpClass(cls):
        os.environ["SITAWARE_DB"] = _DB
        os.environ["SITAWARE_LIVE"] = "1"
        os.environ["SITAWARE_LIVE_SEC"] = "1"
        os.environ["SITAWARE_LLM"] = "0"
        # 本套件是 hermetic 测试（LLM 已关），geocoder 外呼也必须关：
        # 否则有网环境走 nominatim、断网走 offline，test_13 的 offline 断言随环境红绿
        os.environ["SITAWARE_NOMINATIM"] = "0"
        if os.path.exists(_DB):
            os.remove(_DB)
        from sitaware.api_server import app  # 延迟导入，避免 module 级副作用
        # 双保险：若本模块此前已被别的测试导入，env 设置已太晚——直接改实例
        # （GeoService 在 import 时按 env 构造 allow_network）
        try:
            app.state.geocoder.allow_network = False
        except AttributeError:
            pass
        cls._ctx = TestClient(app)
        cls.client = cls._ctx.__enter__()

    @classmethod
    def tearDownClass(cls):
        try:
            cls._ctx.__exit__(None, None, None)
        finally:
            if os.path.exists(_DB):
                try:
                    os.remove(_DB)
                except OSError:
                    pass

    # ------------------------------------------------------------- helpers
    def _first_feature(self):
        feats = self.client.get("/api/events").json()["features"]
        self.assertTrue(feats, "种子事件为空")
        return feats[0]

    # ------------------------------------------------------------- health / metrics
    def test_01_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertGreater(body["events"], 0)

    def test_02_metrics_keys(self):
        r = self.client.get("/api/metrics")
        self.assertEqual(r.status_code, 200)
        m = r.json()
        # 与前端 types.ts 的 Metrics 接口逐键对齐
        for k in ("events_total", "events_today", "high_risk_today", "risk_level", "generated_at"):
            self.assertIn(k, m, f"metrics 缺键 {k}")
        self.assertGreater(m["events_total"], 0)

    # ------------------------------------------------------------- events
    def test_03_events_list_seeded(self):
        r = self.client.get("/api/events")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()["features"]), 0)

    def test_04_events_limit(self):
        r = self.client.get("/api/events", params={"limit": 5})
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(r.json()["features"]), 5)

    def test_05_events_filter_event_type(self):
        et = self._first_feature()["properties"]["event_type"]
        feats = self.client.get("/api/events", params={"event_type": et}).json()["features"]
        self.assertTrue(feats)
        self.assertTrue(all(f["properties"]["event_type"] == et for f in feats))

    def test_06_events_filter_severity(self):
        feats = self.client.get("/api/events", params={"severity": "critical"}).json()["features"]
        self.assertTrue(all(f["properties"]["severity"] == "critical" for f in feats))

    def test_07_events_filter_bbox(self):
        c = self._first_feature()["geometry"]["coordinates"]
        bbox = [c[0] - 0.5, c[1] - 0.5, c[0] + 0.5, c[1] + 0.5]
        feats = self.client.get("/api/events", params={
            "bbox": ",".join(str(x) for x in bbox), "limit": 500}).json()["features"]
        self.assertTrue(feats)
        for f in feats:
            x, y = f["geometry"]["coordinates"]
            self.assertTrue(bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3])

    def test_08_event_get_and_404(self):
        eid = self._first_feature()["id"]
        r = self.client.get(f"/api/events/{eid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], eid)
        self.assertEqual(self.client.get("/api/events/no-such-id-xyz").status_code, 404)

    def test_09_post_event_roundtrip(self):
        body = {"source": "user", "event_type": "custom", "lng": 113.38, "lat": 23.10,
                "severity": "medium", "title": "回归测试事件", "description": "unittest",
                "tags": ["unittest"]}
        r = self.client.post("/api/events", json=body)
        self.assertIn(r.status_code, (200, 201), r.text)
        nid = r.json()["id"]
        back = self.client.get(f"/api/events/{nid}").json()
        self.assertEqual(back["properties"]["title"], "回归测试事件")

    def test_10_post_event_bad_source_422(self):
        body = {"source": "demo", "event_type": "custom", "lng": 113.38, "lat": 23.10}
        self.assertEqual(self.client.post("/api/events", json=body).status_code, 422)

    # ------------------------------------------------------------- situation
    def test_11_summary(self):
        r = self.client.post("/api/situation/summary",
                             json={"lng": 113.37, "lat": 23.10, "radius_km": 10})
        self.assertEqual(r.status_code, 200)
        s = r.json()
        self.assertIn("summary", s)
        self.assertIn("risk_level", s)

    def test_12_query_offline(self):
        r = self.client.post("/api/situation/query", json={"text": "附近有什么高危事件？"})
        self.assertEqual(r.status_code, 200)
        q = r.json()
        self.assertTrue(q.get("answer"))
        self.assertIn(q.get("llm_source"), (None, "template", "local", "ollama"))

    # ------------------------------------------------------------- geocode / route
    def test_13_geocode_address(self):
        r = self.client.post("/api/geocode", json={"text": "广州"})
        self.assertEqual(r.status_code, 200)
        g = r.json()
        self.assertTrue(g["ok"])
        self.assertEqual(g.get("source"), "offline")

    def test_14_geocode_maidenhead(self):
        r = self.client.post("/api/geocode", json={"text": "PM95UR"})
        self.assertEqual(r.status_code, 200)
        g = r.json()
        self.assertTrue(g["ok"])
        self.assertEqual(g.get("grid"), "PM95UR")

    def test_15_route_offline_fallback(self):
        r = self.client.get("/api/route", params={"start_lng": 113.2644, "start_lat": 23.1291,
                                                  "end_lng": 113.38, "end_lat": 23.10})
        self.assertEqual(r.status_code, 200)
        rp = r.json()
        self.assertTrue(rp.get("primary", {}).get("geometry"))
        src = rp["primary"].get("source") or (rp["primary"].get("properties") or {}).get("source")
        # 离线沙箱无 OSRM：必须走直线降级且显式标注，不许静默
        self.assertEqual(src, "fallback_line")

    # ------------------------------------------------------------- alerts
    def test_16_alerts_crud(self):
        body = {"name": "回归规则", "center_lng": 113.37, "center_lat": 23.10,
                "radius_km": 3.0, "min_severity": "high"}
        r = self.client.post("/api/alerts", json=body)
        self.assertIn(r.status_code, (200, 201), r.text)
        aid = r.json()["id"]

        lst = self.client.get("/api/alerts")
        self.assertEqual(lst.status_code, 200)
        rules = lst.json()  # 数组契约（前端 listAlerts(): AlertRule[]）
        self.assertIsInstance(rules, list)
        self.assertTrue(any(x["id"] == aid for x in rules))

        self.assertIn(self.client.delete(f"/api/alerts/{aid}").status_code, (200, 204))
        self.assertEqual(self.client.delete(f"/api/alerts/{aid}").status_code, 404)

    # ------------------------------------------------------------- ham / sse
    def test_17_ham_stations(self):
        r = self.client.get("/api/ham/stations")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.json()["features"]), 0)

    def test_18_sse_route_order(self):
        # TestClient(portal) × sse-starlette 无限流 = 死锁（本机实测连握手都挂起），
        # 故 HTTP 层不跑流；本用例验证等价不变量：路由表中 /api/events/stream
        # 必须注册在 /api/events/{event_id} 之前，否则 "stream" 被当事件 id 捕获 → 404。
        # 帧级验证（ready/event 帧）由真实 uvicorn + TCP 的脚本完成。
        from sitaware.api_server import app
        paths = [getattr(r, "path", None) for r in app.routes]
        self.assertIn("/api/events/stream", paths)
        self.assertIn("/api/events/{event_id}", paths)
        self.assertLess(paths.index("/api/events/stream"),
                        paths.index("/api/events/{event_id}"),
                        "路由顺序错误：stream 必须先于 {event_id} 注册")


if __name__ == "__main__":
    import io

    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SitawareAPITest)
    res = runner.run(suite)
    out = stream.getvalue()
    sys.stderr.write(out)
    with open(r"C:\Users\ASUS\wb_unittest_result.txt", "w", encoding="utf-8") as f:
        f.write(out)
        f.write(f"\n=== passed={res.testsRun - len(res.failures) - len(res.errors)}"
                f" failures={len(res.failures)} errors={len(res.errors)} ===\n")
    sys.exit(0 if res.wasSuccessful() else 1)
