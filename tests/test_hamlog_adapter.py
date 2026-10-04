"""hamlog_adapter 功能测试。

双后端覆盖：
1. HTTP legacy 后端：mock HamLog Flask 契约服务（http.server）——历史 SPEC 契约兼容
2. SQLite 直连后端（默认主路径）：临时 Log.db（HamLog R1.0.0 schema）
覆盖：5 个工具正常路径、卡债方向区分、fail-fast（库不存在/记录不存在）、registry 扫描。
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]

_QSO_1 = {
    "qso_id": 1,
    "callsign": "BG5ABC",
    "freq": "14.074",
    "mode": "FT8",
    "rst_sent": "-05",
    "rst_rcvd": "-12",
    "qso_date": "2026-08-01",
    "band": "20m",
    "power": "10W",
    "qsl_status": "pending",
    "my_callsign": "BI5XXX",
    "my_grid": "PM01",
    "their_grid": "PM02",
    "qso_time_utc": "1200",
}

_DEBTS = [
    {"callsign": "BG5ABC", "qso_date": "2026-08-01", "band": "20m", "mode": "FT8",
     "status": "pending", "direction": "owed"},
    {"callsign": "BD7QQQ", "qso_date": "2026-07-15", "band": "40m", "mode": "SSB",
     "status": "pending", "direction": "owing"},
]


class _MockHamlogHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 静音
        pass

    def _reply(self, code: int, data=None, message: str = "ok"):
        body = json.dumps({"code": code, "message": message, "data": data}, ensure_ascii=False)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        if path == "/api/qso/search":
            callsign = (query.get("callsign") or [""])[0].upper()
            rows = [_QSO_1]
            if callsign and callsign not in _QSO_1["callsign"]:
                rows = []
            self._reply(200, rows)
        elif path == "/api/qsl/debts":
            # 故意忽略 direction 参数，验证 adapter 本地兜底过滤
            self._reply(200, _DEBTS)
        elif path == "/api/qso/1":
            self._reply(200, _QSO_1)
        elif path.startswith("/api/qso/"):
            self._reply(4040, None, message=f"QSO 记录不存在: {path.rsplit('/', 1)[-1]}")
        elif path == "/api/station":
            self._reply(200, {"callsign": "BI5XXX", "grid": "PM01"})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path == "/api/qso":
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not body.get("callsign"):
                self._reply(4000, None, message="缺少呼号")
                return
            self._reply(200, {"qso_id": 99})
        else:
            self.send_response(404)
            self.end_headers()

    def do_PUT(self):
        if urlparse(self.path).path.startswith("/api/qsl/"):
            self._reply(200, {"updated": True})
        else:
            self.send_response(404)
            self.end_headers()


class HamlogAdapterTest(unittest.TestCase):
    server: ThreadingHTTPServer
    _old_env: str | None = None

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHamlogHandler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        port = cls.server.server_address[1]
        cls._old_env = os.environ.get("HAMLOG_API_URL")
        os.environ["HAMLOG_API_URL"] = f"http://127.0.0.1:{port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if cls._old_env is None:
            os.environ.pop("HAMLOG_API_URL", None)
        else:
            os.environ["HAMLOG_API_URL"] = cls._old_env

    # ---- 工具正常路径 ----

    def test_qso_search_returns_records(self):
        from mcpserver.adapters.hamlog_adapter.adapter import qso_search

        rows = qso_search(callsign="BG5ABC", since="2026-01-01", band="20m")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["callsign"], "BG5ABC")
        self.assertEqual(rows[0]["qso_date"], "2026-08-01")
        self.assertEqual(rows[0]["qsl_status"], "pending")

    def test_qsl_debts_distinguishes_direction(self):
        from mcpserver.adapters.hamlog_adapter.adapter import qsl_debts

        owed = qsl_debts(direction="owed")
        owing = qsl_debts(direction="owing")
        all_debts = qsl_debts(direction="all")
        self.assertEqual([d["callsign"] for d in owed], ["BG5ABC"])
        self.assertTrue(all(d["debt_type"] == "i_owe" for d in owed))
        self.assertEqual([d["callsign"] for d in owing], ["BD7QQQ"])
        self.assertTrue(all(d["debt_type"] == "they_owe" for d in owing))
        self.assertEqual(len(all_debts), 2)

    def test_qso_add_and_qsl_update(self):
        from mcpserver.adapters.hamlog_adapter.adapter import qsl_update, qso_add

        added = qso_add(callsign="BG5ABC", qso_date="2026-08-18", mode="FT8", freq="14.074")
        self.assertTrue(added["success"])
        self.assertEqual(added["qso_id"], 99)
        updated = qsl_update(qso_id=99, status="sent", sent_date="2026-08-18")
        self.assertTrue(updated["success"])

    def test_card_content_lines_usable(self):
        from mcpserver.adapters.hamlog_adapter.adapter import card_content

        card = card_content(qso_id=1)
        self.assertEqual(card["my_callsign"], "BI5XXX")
        self.assertEqual(card["my_grid"], "PM01")
        self.assertEqual(card["their_callsign"], "BG5ABC")
        lines = card["content_lines"]
        self.assertEqual(lines[0], "===== QSL INFO =====")
        self.assertIn("TO: BG5ABC", lines)
        self.assertIn("FREQ: 14.074 MHz", lines)
        self.assertIn("MODE: FT8", lines)
        # 能直接逐行抄卡：全为纯文本行
        self.assertTrue(all(isinstance(l, str) and l.strip() for l in lines))

    # ---- fail-fast ----

    def test_hamlog_down_raises_error(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, qso_search

        old = os.environ["HAMLOG_API_URL"]
        os.environ["HAMLOG_API_URL"] = "http://127.0.0.1:1"  # 必拒端口
        try:
            with self.assertRaises(HamlogError) as ctx:
                qso_search(callsign="BG5ABC")
            self.assertIn("不可达", str(ctx.exception))
        finally:
            os.environ["HAMLOG_API_URL"] = old

    def test_business_code_error_translated(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, card_content

        with self.assertRaises(HamlogError) as ctx:
            card_content(qso_id=99999)
        message = str(ctx.exception)
        self.assertIn("QSO 记录不存在", message)  # 人类可读，非裸异常

    def test_handle_handoff_error_envelope(self):
        import asyncio

        from mcpserver.adapters.hamlog_adapter.adapter import HamlogBridge

        bridge = HamlogBridge()
        old = os.environ["HAMLOG_API_URL"]
        os.environ["HAMLOG_API_URL"] = "http://127.0.0.1:1"
        try:
            result = json.loads(
                asyncio.run(bridge.handle_handoff({"tool_name": "hamlog_qso_search", "callsign": "X"}))
            )
            self.assertEqual(result["status"], "error")
            self.assertIn("不可达", result["message"])
        finally:
            os.environ["HAMLOG_API_URL"] = old

        unknown = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
        self.assertEqual(unknown["status"], "error")

    # ---- mcpserver 加载（验收2） ----

    def test_registry_scan_loads_adapter(self):
        from mcpserver import mcp_registry

        mcp_registry.clear_registry()
        try:
            registered = mcp_registry.scan_and_register_mcp_agents(str(REPO_ROOT / "mcpserver"))
            self.assertIn("hamlog_adapter", registered)
            instance = mcp_registry.get_service_instance("hamlog_adapter")
            self.assertTrue(hasattr(instance, "handle_handoff"))
            tools = mcp_registry.get_available_tools("hamlog_adapter")
            self.assertEqual(
                {t["command"] for t in tools},
                {
                    "hamlog_qso_search",
                    "hamlog_qsl_debts",
                    "hamlog_qso_add",
                    "hamlog_qsl_update",
                    "hamlog_card_content",
                },
            )
        finally:
            mcp_registry.clear_registry()


class HamlogSqliteBackendTest(unittest.TestCase):
    """SQLite 直连后端：临时 Log.db，与 HamLog R1.0.0 AutoDeal 建表语句一致。

    注意：unittest.TestCase 保证方法按字母序执行（pytest 不保证），
    因此 roundtrip 测试命名 test_a_* 确保最先跑，后续断言基于其已录入的 JA1XYZ。"""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        import tempfile

        cls._tmpdir = tempfile.mkdtemp(prefix="hamlog_test_")
        cls.db_file = Path(cls._tmpdir) / "Log.db"
        conn = sqlite3.connect(cls.db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Callsign TEXT NOT NULL, Freq TEXT,
                Year INTEGER, Month INTEGER, Day INTEGER, Time TEXT,
                Mode TEXT, Power_self TEXT, Power_side TEXT,
                Rst_self TEXT, Rst_side TEXT, QTH TEXT, Device TEXT,
                QSL_RX TEXT, QSL_SEND TEXT, Remarks TEXT,
                CreateTime TEXT DEFAULT CURRENT_TIMESTAMP)
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO log (Callsign, Freq, Year, Month, Day, Time, Mode, "
                     "Rst_self, Rst_side, QSL_RX, QSL_SEND) "
                     "VALUES ('BG5ABC', '14.074', 2026, 8, 1, '1200', 'FT8', '-12', '-05', '', '')")
        conn.execute("INSERT INTO log (Callsign, Freq, Year, Month, Day, Time, Mode, "
                     "Rst_self, Rst_side, QSL_RX, QSL_SEND) "
                     "VALUES ('BD7QQQ', '7.050', 2026, 7, 15, '0900', 'SSB', '59', '57', '', '20260720')")  # 已发卡未收卡
        conn.execute("INSERT INTO settings VALUES ('my_callsign', 'BI5XXX')")
        conn.execute("INSERT INTO settings VALUES ('my_grid', 'PM01')")
        conn.commit()
        conn.close()
        cls._old_db = os.environ.get("HAMLOG_DB_PATH")
        cls._old_url = os.environ.get("HAMLOG_API_URL")
        os.environ["HAMLOG_DB_PATH"] = str(cls.db_file)
        os.environ.pop("HAMLOG_API_URL", None)  # 不设 URL → SQLite 主路径

    @classmethod
    def tearDownClass(cls):
        if cls._old_db is None:
            os.environ.pop("HAMLOG_DB_PATH", None)
        else:
            os.environ["HAMLOG_DB_PATH"] = cls._old_db
        if cls._old_url is not None:
            os.environ["HAMLOG_API_URL"] = cls._old_url
        import shutil

        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_search_by_callsign_and_date_range(self):
        from mcpserver.adapters.hamlog_adapter.adapter import qso_search

        rows = qso_search(callsign="BG5ABC")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["qso_date"], "2026-08-01")
        self.assertEqual(rows[0]["rst_sent"], "-05")   # Rst_side → rst_sent
        self.assertEqual(rows[0]["rst_rcvd"], "-12")   # Rst_self → rst_rcvd
        ranged = qso_search(since="2026-08-01", until="2026-12-31")
        names = sorted(r["callsign"] for r in ranged)
        if getattr(type(self), "_roundtrip_done", False):
            self.assertEqual(names, ["BG5ABC", "JA1XYZ"])  # JA1XYZ 在 test_a 中录入
        else:
            self.assertEqual(names, ["BG5ABC"])

    def test_qsl_debts_direction(self):  # 依赖 test_a_roundtrip 之后（JA1XYZ 已发卡）
        from mcpserver.adapters.hamlog_adapter.adapter import qsl_debts

        if not getattr(type(self), "_roundtrip_done", False):
            self.skipTest("test_a_roundtrip 未先执行（非字母序运行器）")

        owed = qsl_debts(direction="owed")   # QSL_SEND 空 = 我欠（BD7QQQ 已发卡在 test_a 前缀数据中不在此列；JA1XYZ 已在 test_a 发卡）
        owing = qsl_debts(direction="owing")  # QSL_RX 空 = 欠我
        self.assertEqual(sorted(d["callsign"] for d in owed), ["BG5ABC"])
        self.assertTrue(all(d["debt_type"] == "i_owe" for d in owed))
        self.assertEqual(sorted(d["callsign"] for d in owing), ["BD7QQQ", "BG5ABC", "JA1XYZ"])  # QSL_RX 空 = 未收到回卡（含已发未收）
        self.assertTrue(all(d["debt_type"] == "they_owe" for d in owing))

    def test_a_roundtrip_add_update_card(self):
        # test_a 前缀：unittest 字母序下最先跑，先完成 JA1XYZ 录入+发卡
        from mcpserver.adapters.hamlog_adapter.adapter import card_content, qsl_update, qso_add

        added = qso_add(callsign="ja1xyz", qso_date="2026-08-18", mode="cw", freq="21.2", rst_sent="579")
        self.assertTrue(added["success"])
        qso_id = added["qso_id"]
        self.assertIsInstance(qso_id, int)

        updated = qsl_update(qso_id=qso_id, status="sent", sent_date="2026-08-18")
        self.assertTrue(updated["success"])

        card = card_content(qso_id=qso_id)
        self.assertEqual(card["my_callsign"], "BI5XXX")
        self.assertEqual(card["their_callsign"], "JA1XYZ")
        self.assertIn("MODE: CW", card["content_lines"])
        type(self)._roundtrip_done = True

    def test_missing_db_fails_fast(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, qso_search

        old = os.environ["HAMLOG_DB_PATH"]
        os.environ["HAMLOG_DB_PATH"] = str(Path(self._tmpdir) / "nonexistent" / "Log.db")
        try:
            with self.assertRaises(HamlogError) as ctx:
                qso_search(callsign="X")
            self.assertIn("数据库不存在", str(ctx.exception))
        finally:
            os.environ["HAMLOG_DB_PATH"] = old

    def test_update_unknown_qso_fails_fast(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, qsl_update

        with self.assertRaises(HamlogError) as ctx:
            qsl_update(qso_id=999999, status="sent")
        self.assertIn("未找到", str(ctx.exception))

    def test_band_filter_rejects_unknown_band(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, qso_search

        rows = qso_search(band="20m")
        self.assertEqual([r["callsign"] for r in rows], ["BG5ABC"])  # 14.074 命中 20m 前缀（JA1XYZ 在 21.2）
        with self.assertRaises(HamlogError):
            qso_search(band="3cm")


class HamlogNewToolsTest(unittest.TestCase):
    """Y-01 新增能力测试：ADIF 往返 / DXCC 查询 / 通联统计 / CAT 降级。

    使用独立临时 SQLite DB，不污染 HamlogSqliteBackendTest 的共享 fixture；
    CAT 测试不依赖数据库，任何后端下都应诚实降级返回 ok:False 而不抛异常。"""

    @classmethod
    def setUpClass(cls):
        import sqlite3
        import tempfile

        cls._tmpdir = tempfile.mkdtemp(prefix="hamlog_newtools_")
        cls.db_file = Path(cls._tmpdir) / "Log.db"
        conn = sqlite3.connect(cls.db_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Callsign TEXT NOT NULL, Freq TEXT,
                Year INTEGER, Month INTEGER, Day INTEGER, Time TEXT,
                Mode TEXT, Power_self TEXT, Power_side TEXT,
                Rst_self TEXT, Rst_side TEXT, QTH TEXT, Device TEXT,
                QSL_RX TEXT, QSL_SEND TEXT, Remarks TEXT,
                CreateTime TEXT DEFAULT CURRENT_TIMESTAMP)
        """)
        conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
        # 三条已知记录：2 条 FT8（14.074→20m）+ 1 条 SSB（7.050→40m），仅一条已收卡
        conn.execute("INSERT INTO log (Callsign, Freq, Year, Month, Day, Time, Mode, "
                     "Rst_self, Rst_side, QSL_RX, QSL_SEND) "
                     "VALUES ('JA1ABC', '14.074', 2026, 8, 1, '1200', 'FT8', '-12', '-05', '20260810', '')")
        conn.execute("INSERT INTO log (Callsign, Freq, Year, Month, Day, Time, Mode, "
                     "Rst_self, Rst_side, QSL_RX, QSL_SEND) "
                     "VALUES ('K1ABC', '7.050', 2026, 8, 2, '1300', 'SSB', '59', '59', '', '')")
        conn.execute("INSERT INTO log (Callsign, Freq, Year, Month, Day, Time, Mode, "
                     "Rst_self, Rst_side, QSL_RX, QSL_SEND) "
                     "VALUES ('VK2XYZ', '14.074', 2026, 8, 3, '1400', 'FT8', '-10', '-03', '', '')")
        conn.execute("INSERT INTO settings VALUES ('my_callsign', 'BI5XXX')")
        conn.execute("INSERT INTO settings VALUES ('my_grid', 'PM01')")
        conn.commit()
        conn.close()
        cls._old_db = os.environ.get("HAMLOG_DB_PATH")
        cls._old_url = os.environ.get("HAMLOG_API_URL")
        os.environ["HAMLOG_DB_PATH"] = str(cls.db_file)
        os.environ.pop("HAMLOG_API_URL", None)  # 不设 URL → SQLite 主路径

    @classmethod
    def tearDownClass(cls):
        if cls._old_db is None:
            os.environ.pop("HAMLOG_DB_PATH", None)
        else:
            os.environ["HAMLOG_DB_PATH"] = cls._old_db
        if cls._old_url is not None:
            os.environ["HAMLOG_API_URL"] = cls._old_url
        import shutil

        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def test_adif_export_import_roundtrip(self):
        """导出的 ADIF 能被 import 回来（写入独立空库，避免污染统计断言）。"""
        import sqlite3

        from mcpserver.adapters.hamlog_adapter.adapter import adif_export, adif_import

        exported = adif_export()
        self.assertGreaterEqual(exported["count"], 3)
        self.assertIn("<EOH>", exported["adif"])
        self.assertIn("<CALL:", exported["adif"])
        self.assertIn("<EOR>", exported["adif"])

        fresh = Path(self._tmpdir) / "Fresh.db"
        conn = sqlite3.connect(fresh)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                Callsign TEXT NOT NULL, Freq TEXT,
                Year INTEGER, Month INTEGER, Day INTEGER, Time TEXT,
                Mode TEXT, Power_self TEXT, Power_side TEXT,
                Rst_self TEXT, Rst_side TEXT, QTH TEXT, Device TEXT,
                QSL_RX TEXT, QSL_SEND TEXT, Remarks TEXT,
                CreateTime TEXT DEFAULT CURRENT_TIMESTAMP)
        """)
        conn.commit()
        conn.close()

        old = os.environ["HAMLOG_DB_PATH"]
        os.environ["HAMLOG_DB_PATH"] = str(fresh)
        try:
            result = adif_import(exported["adif"])
            self.assertEqual(result["failed"], 0)
            self.assertEqual(result["success"], exported["count"])
        finally:
            os.environ["HAMLOG_DB_PATH"] = old

    def test_adif_import_skips_bad_records(self):
        from mcpserver.adapters.hamlog_adapter.adapter import adif_import

        bad = "<CALL:5>JA1ZZ <EOR>\n<MODE:3>FT8 <EOR>\n"  # 第一条缺 MODE，第二条缺 CALL
        result = adif_import(bad)
        self.assertEqual(result["success"], 0)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["total"], 2)

    def test_dxcc_lookup_hit(self):
        from mcpserver.adapters.hamlog_adapter.adapter import dxcc_lookup

        self.assertEqual(dxcc_lookup("JA1ABC"), {"prefix": "JA", "entity": "Japan", "continent": "Asia"})
        self.assertEqual(dxcc_lookup("VE3XYZ")["entity"], "Canada")
        self.assertEqual(dxcc_lookup("K5ABC")["entity"], "United States")
        self.assertEqual(dxcc_lookup("BY1AA")["entity"], "China")
        # 带便携斜杠后缀也能命中主前缀
        self.assertEqual(dxcc_lookup("JA1ABC/2")["prefix"], "JA")

    def test_dxcc_lookup_miss(self):
        from mcpserver.adapters.hamlog_adapter.adapter import HamlogError, dxcc_lookup

        with self.assertRaises(HamlogError):
            dxcc_lookup("1A0XX")  # 非精简表内前缀

    def test_hamlog_stats_counts(self):
        from mcpserver.adapters.hamlog_adapter.adapter import hamlog_stats

        stats = hamlog_stats()
        self.assertEqual(stats["total_qsos"], 3)
        self.assertEqual(stats["by_mode"], {"FT8": 2, "SSB": 1})
        self.assertEqual(stats["by_band"], {"20m": 2, "40m": 1})
        self.assertEqual(stats["qsl_confirmed"], 1)

    def test_cat_get_freq_no_radio_returns_ok_false(self):
        from mcpserver.adapters.hamlog_adapter.adapter import hamlog_cat_get_freq

        result = hamlog_cat_get_freq()  # 无电台/无 rsba1 包时诚实降级，不抛裸异常
        self.assertIsInstance(result, dict)
        self.assertFalse(result["ok"])
        self.assertIn("error", result)
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
