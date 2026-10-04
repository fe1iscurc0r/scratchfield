"""盲区 ②-1/③-1 验收测试：认知免疫信任评分 + ADR 机制。

验收标准（源自 docs/授粉落地字据-2026-08-23.md）：
- ②-1: grep -r "trust_score" mcpserver/ 命中，信任评分表落盘 + 低信任自动隔离
- ③-1: docs/adr/ 目录存在，每次大决策一条 ADR
（①-1 战情面板由并行会话 apiserver+EventBus 实现覆盖，84b3d049）
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
from pathlib import Path

from mcpserver.trust_layer import TrustScorer, score_source


class TestTrustScorer:
    def test_source_scoring(self):
        """来源评分：可信 +1 / 黑名单 -2 / 未知 0"""
        assert score_source("github.com/fe1iscurc0r/work-specs")[0] == 1
        assert score_source("github.com/unknown-malware/repo")[0] == -2
        assert score_source("example.com/random")[0] == 0
        assert score_source("")[0] == 0

    def test_assess_trusted_signed_reviewed(self):
        """可信源+签名+review → 高信任，不隔离"""
        scorer = TrustScorer(store_path=Path("/tmp/test-trust-scores.json"))
        a = scorer.assess("good-lib", source="github.com/fe1iscurc0r/x",
                          signature=True, lineage="main", reviewed=True)
        assert a.score >= 2
        assert a.quarantined is False

    def test_assess_untrusted_quarantined(self):
        """黑名单源 → 低信任，自动隔离"""
        scorer = TrustScorer(store_path=Path("/tmp/test-trust-scores.json"))
        a = scorer.assess("evil-lib", source="github.com/unknown-malware/x")
        assert a.score <= 0
        assert a.quarantined is True

    def test_assess_persists_to_disk(self):
        """评分表落盘，可回溯"""
        store = Path("/tmp/test-trust-persist.json")
        if store.exists():
            store.unlink()
        scorer = TrustScorer(store_path=store)
        scorer.assess("pkg-a", source="pypi.org/requests", signature=True)
        assert store.exists()
        data = json.loads(store.read_text(encoding="utf-8"))
        assert "pkg-a" in data
        assert data["pkg-a"]["score"] >= 2

    def test_quarantine_list(self):
        scorer = TrustScorer(store_path=Path("/tmp/test-trust-scores.json"))
        scorer.assess("bad-a", source="github.com/unknown-malware/a")
        scorer.assess("ok-b", source="github.com/fe1iscurc0r/b", signature=True)
        names = [q["name"] for q in scorer.quarantine_list()]
        assert "bad-a" in names
        assert "ok-b" not in names

    def test_gate_registration_no_metadata_passthrough(self):
        """无信任元数据的 manifest 直接放行（不改变现状）"""
        from mcpserver.mcp_registry import _trust_gate_registration
        assert _trust_gate_registration({"name": "legacy"}, Path("x")) is None

    def test_gate_registration_low_trust_blocked(self):
        """带黑名单 source 的 manifest 被拦截"""
        from mcpserver.mcp_registry import _trust_gate_registration
        reason = _trust_gate_registration(
            {"name": "suspicious", "source": "github.com/unknown-malware/z"},
            Path("x"),
        )
        assert reason is not None
        assert "隔离区" in reason


# ─────────────────────────── ③-1 ADR 决策日志 ───────────────────────────

class TestAdr:
    def test_adr_dir_exists(self):
        """docs/adr/ 目录存在且有 README 索引"""
        adr_dir = Path(__file__).resolve().parent.parent / "docs" / "adr"
        assert adr_dir.is_dir()
        assert (adr_dir / "README.md").exists()

    def test_adr_files_present(self):
        """至少一条 ADR 落盘（大决策可回溯）"""
        adr_dir = Path(__file__).resolve().parent.parent / "docs" / "adr"
        adrs = list(adr_dir.glob("ADR-*.md"))
        assert len(adrs) >= 1
