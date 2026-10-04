"""F-01 Trace Integrity 审计器验收测试（≥6 用例）。

验收标准（源自 TRAE_WORKORDER_PROMPT_AGENT_FOXTROT.md）：
- 合法记录全过 / 缺字段拦截 / 时间戳乱序 / 无来源拦截 / 回放缺口 / 报告生成
"""

from mcpserver.trace_audit.audit import audit, check_schema
from mcpserver.trace_audit.schema import parse_timestamp


def _valid_record(**overrides):
    rec = {
        "id": "delivery-001",
        "timestamp": 1700000000.0,
        "source": "github.com/fe1iscurc0r/scratchpad",
        "type": "delivery",
        "owner": "foxtrot",
    }
    rec.update(overrides)
    return rec


class TestCheckSchema:
    def test_legal_record_ok(self):
        assert check_schema(_valid_record()) == []

    def test_missing_field_detected(self):
        rec = {"id": "x", "timestamp": 1, "type": "delivery", "owner": "a"}
        issues = check_schema(rec)
        assert any("source" in i for i in issues)

    def test_bad_timestamp_type_detected(self):
        issues = check_schema(_valid_record(timestamp="not-a-date"))
        assert any("timestamp" in i for i in issues)


class TestAudit:
    def test_legal_record_passes(self):
        rep = audit([_valid_record()])
        assert rep.verdict == "PASS"
        assert all(rep.criteria.values())

    def test_missing_field_blocked(self):
        rec = _valid_record()
        del rec["source"]
        rep = audit([rec])
        assert rep.verdict == "FAIL"
        assert rep.criteria["schema_valid"] is False

    def test_timestamp_out_of_order(self):
        r1 = _valid_record(id="a", timestamp=200.0)
        r2 = _valid_record(id="b", timestamp=100.0)
        rep = audit([r1, r2])
        assert rep.verdict == "FAIL"
        assert rep.criteria["replayable"] is False

    def test_no_source_blocked(self):
        rep = audit([_valid_record(source="")])
        assert rep.verdict == "FAIL"
        assert rep.criteria["source_traceable"] is False

    def test_replay_gap(self):
        rep = audit([_valid_record(id="a", timestamp=None)])
        assert rep.criteria["replayable"] is False

    def test_id_duplicate(self):
        rep = audit([_valid_record(id="dup"), _valid_record(id="dup", source="other")])
        assert rep.criteria["id_unique"] is False

    def test_report_generation_grep(self):
        rep = audit([_valid_record(), _valid_record(id="dup"), _valid_record(id="dup")])
        text = rep.to_text()
        assert "VERDICT" in text
        assert "CRITERION[schema_valid]" in text
        assert "ISSUE" in text
