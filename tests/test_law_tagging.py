"""卷164：判决书自动打标层测试。

覆盖工单 E1/E2：
- von_client：协议调用 / 问题类型校验 / **断路器**（连续 5 次失败熔断 60s、
  冷却后半开恢复）/ 探活降级 / 未启用快速失败
- 打标蓝图：从 ``domains/law/pack.yaml`` 读取（不写死在代码）
- 喂料策略：当事人+案由+诉讼请求+本院认为 拼接、≤4k 截断不炸
- 低置信分流：choice <0.6 不入库、进 ``_queue/``
- 人工确认：置信改记 1.0(人工)
- tag_confidence migration：存量库（无该列）自动 ALTER TABLE 兼容
- **集成**：mock von serve 跑通「导入→打标→低置信进队列→人工确认」全链路

不依赖真实 Von 服务（工单要求 mock）。
"""

from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domains.law.importers import tagging  # noqa: E402

# ===========================================================================
# mock von serve
# ===========================================================================

#: mock 返回的固定概率（案由高置信、争议焦点低置信）。
MOCK_ANSWERS = {
    "案由分类": {
        "value": "合同纠纷", "confidence": 0.87,
        "probs": {"合同纠纷": 0.87, "侵权责任纠纷": 0.08, "婚姻家庭纠纷": 0.05},
    },
    "审理程序": {
        "value": "二审", "confidence": 0.91,
        "probs": {"一审": 0.05, "二审": 0.91, "再审": 0.03, "执行": 0.01},
    },
    "是否指导性案例": {"value": False, "confidence": 0.95},
    "争议焦点归类": {
        "value": "事实认定", "confidence": 0.42,
        "probs": {"事实认定": 0.42, "法律适用": 0.38, "程序问题": 0.20},
    },
}


class _VonHandler(BaseHTTPRequestHandler):
    """极简 `/v1/systemone` mock：按 questions 回固定概率。"""

    #: 类级计数，供测试断言「调用了几次」。
    calls = 0
    fail_mode = False
    delay = 0.0

    def log_message(self, *args):  # noqa: D102 - 静默
        pass

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def do_POST(self):  # noqa: N802
        type(self).calls += 1
        if type(self).delay:
            time.sleep(type(self).delay)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if type(self).fail_mode:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"error":"boom"}')
            return
        questions = body.get("questions") or {}
        answers = {k: MOCK_ANSWERS[k] for k in questions if k in MOCK_ANSWERS}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"answers": answers}).encode())


@pytest.fixture()
def mock_von():
    """起一个本地 mock von serve，返回 (endpoint, handler_cls)。"""
    _VonHandler.calls = 0
    _VonHandler.fail_mode = False
    _VonHandler.delay = 0.0
    srv = HTTPServer(("127.0.0.1", 0), _VonHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}", _VonHandler
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture()
def von(mock_von):
    """构造指向 mock 的 VonClient。"""
    from apiserver.von_client import VonClient

    endpoint, handler = mock_von
    client = VonClient(
        endpoint, timeout=5.0, breaker_threshold=5, breaker_cooldown=0.3, enabled=True
    )
    return client, handler


# ===========================================================================
# A. von_client：协议 / 断路器 / 降级
# ===========================================================================

QUESTIONS = {
    "案由分类": {"type": "choice", "options": ["合同纠纷", "侵权责任纠纷", "婚姻家庭纠纷"]},
    "审理程序": {"type": "choice", "options": ["一审", "二审", "再审", "执行"]},
    "是否指导性案例": {"type": "boolean"},
}


def test_ask_returns_answers(von):
    client, _ = von
    res = client.ask({"context": "某判决书摘要"}, QUESTIONS)
    assert "answers" in res
    assert res["answers"]["案由分类"]["value"] == "合同纠纷"
    assert res["answers"]["案由分类"]["confidence"] == pytest.approx(0.87)


def test_ask_records_success_and_closes_breaker(von):
    client, _ = von
    client.ask({"context": "x"}, QUESTIONS)
    assert client.breaker_state == "closed"


def test_ask_rejects_unknown_question_type(von):
    from apiserver.von_client import VonError

    client, _ = von
    with pytest.raises(VonError, match="不支持"):
        client.ask({"context": "x"}, {"q": {"type": "ranking"}})


def test_ask_rejects_choice_without_options(von):
    from apiserver.von_client import VonError

    client, _ = von
    with pytest.raises(VonError, match="options"):
        client.ask({"context": "x"}, {"q": {"type": "choice"}})


def test_ask_rejects_empty_questions(von):
    from apiserver.von_client import VonError

    client, _ = von
    with pytest.raises(VonError, match="不能为空"):
        client.ask({"context": "x"}, {})


def test_breaker_opens_after_5_failures(von):
    """连续 5 次失败 → 熔断；第 6 次快速失败（不发起请求）。"""
    from apiserver.von_client import VonCircuitOpen, VonError

    client, handler = von
    handler.fail_mode = True
    for _ in range(5):
        with pytest.raises(VonError):
            client.ask({"context": "x"}, QUESTIONS)
    assert client.breaker_state == "open"
    before = handler.calls
    with pytest.raises(VonCircuitOpen):
        client.ask({"context": "x"}, QUESTIONS)
    assert handler.calls == before, "熔断期内不应再发起真实请求"


def test_breaker_half_open_then_recovers(von):
    """冷却结束后半开探测；mock 恢复健康 → 断路器回到 closed。"""
    from apiserver.von_client import VonError

    client, handler = von
    handler.fail_mode = True
    for _ in range(5):
        with pytest.raises(VonError):
            client.ask({"context": "x"}, QUESTIONS)
    assert client.breaker_state == "open"

    handler.fail_mode = False
    time.sleep(0.35)  # 超过 cooldown=0.3
    res = client.ask({"context": "x"}, QUESTIONS)
    assert res["answers"]["案由分类"]["value"] == "合同纠纷"
    assert client.breaker_state == "closed"


def test_disabled_client_raises_unavailable(mock_von):
    from apiserver.von_client import VonClient, VonUnavailable

    endpoint, _ = mock_von
    client = VonClient(endpoint, enabled=False)
    assert client.status()["alive"] is False
    with pytest.raises(VonUnavailable):
        client.ask({"context": "x"}, QUESTIONS)


def test_probe_false_when_server_down():
    """探活失败返回 False，不抛异常。"""
    from apiserver.von_client import VonClient

    client = VonClient("http://127.0.0.1:1", timeout=0.3, enabled=True)
    assert client.is_alive(force=True) is False


def test_status_shape(von):
    client, _ = von
    st = client.status()
    assert set(st) >= {"enabled", "alive", "endpoint", "breaker", "message"}
    assert st["alive"] is True


# ===========================================================================
# B. 打标蓝图：来自 pack.yaml
# ===========================================================================


def test_blueprint_loaded_from_pack_yaml():
    from apiserver.domain_pack import get_pack

    pack = get_pack("law")
    assert pack is not None, "law 领域包未加载"
    qs = tagging.questions_from_pack(pack)
    assert set(qs) == {"案由分类", "审理程序", "是否指导性案例", "争议焦点归类"}
    assert qs["案由分类"]["type"] == "choice"
    assert len(qs["案由分类"]["options"]) >= 5
    assert qs["审理程序"]["options"] == ["一审", "二审", "再审", "执行"]
    assert qs["是否指导性案例"]["type"] == "boolean"


def test_blueprint_questions_are_von_compatible():
    """蓝图必须能通过 von_client 的问题校验。"""
    from apiserver.domain_pack import get_pack
    from apiserver.von_client import VonClient

    qs = tagging.questions_from_pack(get_pack("law"))
    VonClient._validate_questions(qs)  # 不抛即通过


# ===========================================================================
# C. 喂料策略
# ===========================================================================

JUDGMENT_BODY = """上诉人（原审被告）：北京华宇科技有限公司，住所地北京市朝阳区。
被上诉人（原审原告）：上海明德贸易有限公司，住所地上海市浦东新区。
上诉人北京华宇科技有限公司因买卖合同纠纷一案，向本院提起上诉。
诉讼请求：1. 撤销一审判决；2. 改判驳回被上诉人全部诉讼请求。
本院认为，本案二审争议焦点为合同履行中的付款义务认定。根据《中华人民共和国民法典》
第五百零九条的规定，当事人应当按照约定全面履行自己的义务。
裁判日期：2023年11月20日
"""


def test_feed_context_includes_key_sections():
    ctx, truncated = tagging.build_feed_context(
        parties=["上诉人：北京华宇科技有限公司", "被上诉人：上海明德贸易有限公司"],
        cause_of_action="买卖合同纠纷",
        court="北京市第三中级人民法院",
        trial_level="二审",
        content=JUDGMENT_BODY,
    )
    assert "【当事人】" in ctx
    assert "买卖合同纠纷" in ctx
    assert "【诉讼请求】" in ctx
    assert "【本院认为】" in ctx
    assert truncated is False
    # 诉讼请求段不得吞掉「本院认为」
    claim_seg = ctx.split("【诉讼请求】")[1].split("【本院认为】")[0]
    assert "本院认为" not in claim_seg


def test_feed_context_truncates_long_content():
    """超长正文（多段真实结构）→ 总长 ≤ MAX_CONTEXT_CHARS 且 truncated=True。"""
    big = (
        "诉讼请求：" + "请求判令被告支付货款并承担违约责任。" * 400
        + "\n本院认为，" + "一审认定事实清楚、适用法律正确。" * 400
    )
    ctx, truncated = tagging.build_feed_context(
        parties=["原告：张三", "被告：李四"],
        cause_of_action="买卖合同纠纷",
        court="北京市第三中级人民法院",
        trial_level="二审",
        content=big,
    )
    assert len(ctx) <= tagging.MAX_CONTEXT_CHARS, f"喂料超预算: {len(ctx)}"
    assert truncated is True


def test_feed_context_budget_never_exceeded():
    """无论输入多大，输出恒 ≤ 预算（含兜底路径）。"""
    huge = "无关内容" * 10000
    ctx, _ = tagging.build_feed_context(content=huge)
    assert len(ctx) <= tagging.MAX_CONTEXT_CHARS


def test_feed_context_never_raises_on_empty():
    ctx, truncated = tagging.build_feed_context()
    assert ctx == ""
    assert truncated is False


# ===========================================================================
# D. 低置信分流 + tags 格式
# ===========================================================================


def _tagging_with_fixed(von_client, case_no="test-001"):
    return tagging.tag_case(
        parties=["原告：张三", "被告：李四"],
        cause_of_action="买卖合同纠纷",
        court="北京市第三中级人民法院",
        trial_level="二审",
        content=JUDGMENT_BODY,
        case_no=case_no,
        client=von_client,
    )


def test_low_confidence_routing(von):
    client, _ = von
    result = _tagging_with_fixed(client)
    # 案由 0.87 / 程序 0.91 / 布尔 → 入库
    assert "案由分类" in result.accepted_tags()
    assert "审理程序" in result.accepted_tags()
    # 争议焦点 0.42 < 0.6 → 不入库、进低置信
    assert "争议焦点归类" not in result.accepted_tags()
    assert "争议焦点归类" in result.low_confidence


def test_tags_list_format(von):
    client, _ = von
    result = _tagging_with_fixed(client)
    tags = result.tags_list()
    assert isinstance(tags, list)
    assert "案由分类:合同纠纷" in tags
    assert "审理程序:二审" in tags
    # 布尔 false 不写入
    assert not any(t.startswith("是否指导性案例") for t in tags)


def test_confidence_field_is_valid_json(von):
    client, _ = von
    result = _tagging_with_fixed(client)
    payload = json.loads(result.confidence_field())
    assert payload["threshold"] == tagging.LOW_CONFIDENCE_THRESHOLD
    assert payload["questions"]["案由分类"]["value"] == "合同纠纷"
    assert "争议焦点归类" in payload["low_confidence"]


def test_low_confidence_enqueued(tmp_path, monkeypatch, von):
    client, _ = von
    monkeypatch.setattr(tagging, "QUEUE_DIR", tmp_path / "_queue")
    result = _tagging_with_fixed(client)
    path = tagging.enqueue_low_confidence(result, filename="judgment.docx")
    assert path is not None and path.is_file()
    meta = json.loads(path.read_text(encoding="utf-8"))
    assert meta["case_no"] == "test-001"
    assert "争议焦点归类" in meta["low_confidence"]
    listed = tagging.list_low_confidence_queue()
    assert len(listed) == 1


def test_no_enqueue_when_all_accepted(von, monkeypatch, tmp_path):
    """全部高置信时不写队列。"""
    client, _ = von
    monkeypatch.setattr(tagging, "QUEUE_DIR", tmp_path / "_queue")
    result = _tagging_with_fixed(client)
    result.low_confidence.clear()
    assert tagging.enqueue_low_confidence(result) is None


# ===========================================================================
# E. 人工确认
# ===========================================================================


def test_human_confirm_sets_confidence_and_source():
    original = json.dumps({
        "questions": {"争议焦点归类": {"value": "事实认定", "confidence": 0.42,
                                     "source": "von", "accepted": False}},
        "low_confidence": {"争议焦点归类": {"value": "事实认定", "confidence": 0.42}},
        "threshold": 0.6,
    })
    updated = json.loads(tagging.human_confirm(original, "争议焦点归类", "法律适用"))
    q = updated["questions"]["争议焦点归类"]
    assert q["value"] == "法律适用"
    assert q["confidence"] == tagging.HUMAN_CONFIRMED_CONFIDENCE == 1.0
    assert q["source"] == tagging.HUMAN_CONFIRMED_SOURCE == "人工"
    assert q["accepted"] is True
    assert "争议焦点归类" not in updated["low_confidence"]


def test_human_confirm_handles_empty_and_broken_json():
    assert json.loads(tagging.human_confirm(None, "案由分类", "合同纠纷"))[
        "questions"]["案由分类"]["value"] == "合同纠纷"
    assert json.loads(tagging.human_confirm("{broken", "案由分类", "合同纠纷"))[
        "questions"]["案由分类"]["source"] == "人工"


# ===========================================================================
# F. tag_confidence migration（存量库兼容）
# ===========================================================================


def test_migration_adds_tag_confidence_to_legacy_db(tmp_path):
    """模拟存量库（无 tag_confidence / source 等列），验证自动补列且数据不丢。"""
    import sqlite3

    from apiserver.routes import papers as P

    legacy = tmp_path / "papers.db"
    conn = sqlite3.connect(legacy)
    conn.execute("""
        CREATE TABLE papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, doi TEXT, authors TEXT, journal TEXT,
            year INTEGER, tags TEXT, notes TEXT, abstract TEXT,
            md_path TEXT, linked_experiments TEXT, created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO papers (title, tags, created_at) VALUES (?,?,?)",
        ("旧文献", json.dumps(["旧标签"]), "2020-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()

    monkeypatch_db = tmp_path / "papers" / "papers.db"
    monkeypatch_db.parent.mkdir(parents=True, exist_ok=True)
    import shutil

    shutil.copy(legacy, monkeypatch_db)

    from contextlib import closing

    conn = P._connect.__wrapped__() if hasattr(P._connect, "__wrapped__") else None
    # 直接走 _connect 需 patch 数据目录；改为手工复现迁移逻辑
    conn = sqlite3.connect(monkeypatch_db)
    conn.row_factory = sqlite3.Row
    conn.executescript(P._SCHEMA)
    added = P._migrate_extra_columns(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(papers)")}
    with closing(conn):
        pass

    assert "tag_confidence" in cols, "迁移未补 tag_confidence 列"
    assert "case_no" in cols
    assert "tag_confidence" in added
    # 存量行仍可读
    conn = sqlite3.connect(monkeypatch_db)
    row = conn.execute("SELECT title, tags FROM papers WHERE id=1").fetchone()
    assert row[0] == "旧文献"
    assert json.loads(row[1]) == ["旧标签"]
    conn.close()


def test_migration_idempotent(tmp_path):
    """重复迁移不报错、不重复加列。"""
    import sqlite3

    from apiserver.routes import papers as P

    db = tmp_path / "p.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(P._SCHEMA)
    first = P._migrate_extra_columns(conn)
    second = P._migrate_extra_columns(conn)
    assert second == []
    assert "tag_confidence" in first
    conn.close()


# ===========================================================================
# G. 集成：导入 → 打标 → 低置信进队列 → 人工确认（mock von serve）
# ===========================================================================


@pytest.fixture()
def law_client(tmp_path, monkeypatch, mock_von):
    """TestClient（独立数据目录 + 指向 mock von 的配置）。

    ``system.config.get_data_dir`` 固定返回 ``%APPDATA%/lumo``，因此这里
    直接 patch 它指向 tmp_path，保证每个用例的 papers.db 相互隔离。
    """
    from fastapi.testclient import TestClient

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    import system.config as syscfg

    monkeypatch.setattr(syscfg, "get_data_dir", lambda: data_dir)

    endpoint, _ = mock_von
    cfg = syscfg.get_config()
    monkeypatch.setattr(cfg.von, "enabled", True)
    monkeypatch.setattr(cfg.von, "endpoint", endpoint)
    monkeypatch.setattr(cfg.von, "timeout", 5.0)

    from apiserver.von_client import reset_von_client

    reset_von_client()

    # papers.py 以 `from system.config import get_data_dir` 方式引用，需一并 patch
    from apiserver.routes import papers as _papers

    monkeypatch.setattr(_papers, "get_data_dir", lambda: data_dir)

    monkeypatch.setattr(tagging, "QUEUE_DIR", tmp_path / "_queue")

    import apiserver.api_server as srv

    return TestClient(srv.app), tmp_path


def _make_docx(path: Path, text: str) -> None:
    import docx

    d = docx.Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    d.save(str(path))


LEGACY_JUDGMENT = """北京市第三中级人民法院
民事判决书
（2023）京03民终12345号
上诉人（原审被告）：北京华宇科技有限公司，住所地北京市朝阳区。
法定代表人：张某，董事长。
被上诉人（原审原告）：上海明德贸易有限公司，住所地上海市浦东新区。
法定代表人：李某，总经理。
上诉人北京华宇科技有限公司因与被上诉人上海明德贸易有限公司买卖合同纠纷一案，
不服北京市朝阳区人民法院（2023）京0105民初6789号民事判决，向本院提起上诉。
诉讼请求：1. 撤销一审判决；2. 改判驳回被上诉人全部诉讼请求。
本院认为，本案二审争议焦点为合同履行中的付款义务认定，根据民法典相关规定，
一审认定事实清楚、适用法律正确，上诉请求不能成立。
裁判日期：2023年11月20日
审判长　王某
书记员　孙某
"""


def test_von_status_endpoint(law_client):
    client, _ = law_client
    r = client.get("/api/domains/law/von-status")
    assert r.status_code == 200
    body = r.json()
    assert body["alive"] is True
    assert body["enabled"] is True


def test_full_chain_import_tag_queue_confirm(law_client):
    """全链路：导入（auto_tag）→ tags 落库 → 低置信入队 → 人工确认。"""
    client, tmp_path = law_client
    docx_path = tmp_path / "judgment.docx"
    _make_docx(docx_path, LEGACY_JUDGMENT)

    with docx_path.open("rb") as fh:
        r = client.post(
            "/api/domains/law/import-cases",
            files=[("files", ("judgment.docx", fh.read(),
                              "application/vnd.openxmlformats-officedocument"
                              ".wordprocessingml.document"))],
            data={"source": "pkulaw", "auto_tag": "true"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["imported"] == 1
    tc = body["tagging"]
    assert tc["skipped"] is False
    assert tc["low_confidence"] == 1, f"应有 1 条低置信: {tc}"

    pid = body["inserted"][0]["id"]

    # tags 落库（键值对格式）
    papers = client.get("/api/papers", params={"limit": 10}).json()["papers"]
    row = next(p for p in papers if p["id"] == pid)
    assert "案由分类:合同纠纷" in row["tags"]
    assert "审理程序:二审" in row["tags"]
    assert row["tag_confidence"]

    # 低置信进队列
    q = client.get("/api/domains/law/tag-queue").json()
    assert q["count"] == 1
    assert q["items"][0]["low_confidence"], "队列项应含低置信标签明细"
    assert "争议焦点归类" in q["items"][0]["low_confidence"]

    # 人工确认
    r = client.post(
        "/api/domains/law/tag-confirm",
        json={"id": pid, "question": "争议焦点归类", "value": "法律适用"},
    )
    assert r.status_code == 200, r.text
    confirm = r.json()
    assert confirm["source"] == "人工"
    assert confirm["confidence"] == 1.0
    assert confirm["queue_entry_removed"] is True

    conf = json.loads(confirm["paper"]["tag_confidence"])
    assert conf["questions"]["争议焦点归类"]["source"] == "人工"
    assert "争议焦点归类:法律适用" in confirm["paper"]["tags"]
    # 队列已清空
    assert client.get("/api/domains/law/tag-queue").json()["count"] == 0


def test_import_auto_tag_false_skips(law_client):
    """auto_tag=false 时不打标、不写 tags。"""
    client, tmp_path = law_client
    docx_path = tmp_path / "j2.docx"
    _make_docx(docx_path, LEGACY_JUDGMENT)
    with docx_path.open("rb") as fh:
        r = client.post(
            "/api/domains/law/import-cases",
            files=[("files", ("j2.docx", fh.read(), "application/octet-stream"))],
            data={"source": "manual", "auto_tag": "false"},
        )
    body = r.json()
    assert body["tagging"]["skipped"] is True
    pid = body["inserted"][0]["id"]
    papers = client.get("/api/papers", params={"limit": 10}).json()["papers"]
    row = next(p for p in papers if p["id"] == pid)
    assert not row.get("tags")


def test_tag_pending_preview_and_tag_cases(law_client):
    """手动批量：预览待打标数 + tag-cases 打标。"""
    client, tmp_path = law_client
    docx_path = tmp_path / "j3.docx"
    _make_docx(docx_path, LEGACY_JUDGMENT)
    with docx_path.open("rb") as fh:
        client.post(
            "/api/domains/law/import-cases",
            files=[("files", ("j3.docx", fh.read(), "application/octet-stream"))],
            data={"source": "manual", "auto_tag": "false"},
        )

    prev = client.get("/api/domains/law/tag-pending-preview").json()
    assert prev["pending"] == 1
    assert prev["von"]["alive"] is True

    r = client.post("/api/domains/law/tag-cases", json={"ids": [], "only_untagged": True})
    body = r.json()
    assert body["von_available"] is True
    assert body["processed"] == 1
    assert body["low_confidence"] == 1

    # 再预览应为 0（已打标）
    assert client.get("/api/domains/law/tag-pending-preview").json()["pending"] == 0


def test_tag_pending_alias_endpoint(law_client):
    """工单要求的 POST /tag-pending 别名可用，且只处理无标签判例。"""
    client, tmp_path = law_client
    docx_path = tmp_path / "j4.docx"
    _make_docx(docx_path, LEGACY_JUDGMENT)
    with docx_path.open("rb") as fh:
        client.post(
            "/api/domains/law/import-cases",
            files=[("files", ("j4.docx", fh.read(), "application/octet-stream"))],
            data={"source": "manual", "auto_tag": "false"},
        )
    r = client.post("/api/domains/law/tag-pending", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["von_available"] is True
    assert body["processed"] == 1
    # 幂等：再调一次不应重复处理
    assert client.post("/api/domains/law/tag-pending", json={}).json()["processed"] == 0


def test_tag_pending_alias_endpoint(law_client):
    """工单要求的 POST /tag-pending 别名可用，且只处理无标签判例。"""
    client, tmp_path = law_client
    docx_path = tmp_path / "j4.docx"
    _make_docx(docx_path, LEGACY_JUDGMENT)
    with docx_path.open("rb") as fh:
        client.post(
            "/api/domains/law/import-cases",
            files=[("files", ("j4.docx", fh.read(), "application/octet-stream"))],
            data={"source": "manual", "auto_tag": "false"},
        )
    r = client.post("/api/domains/law/tag-pending", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["von_available"] is True
    assert body["processed"] == 1
    # 幂等：再调一次不应重复处理
    assert client.post("/api/domains/law/tag-pending", json={}).json()["processed"] == 0
