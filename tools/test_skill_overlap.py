"""skill_overlap 语义重叠检测验收硬线（84号 A1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.orchestration.skill_overlap import detect_overlap, tokenize  # noqa: E402


def _existing(name: str, text: str) -> dict:
    return {"name": name, "text": text}


def test_similar_skill_detected():
    """同主题 skill 文本 → 相似度 > 阈值（建议合并）。"""
    new = "发送邮件：根据收件人、主题、正文，通过 SMTP 发送 email，支持附件与抄送。"
    existing = [
        _existing("send-mail", "发送邮件技能：使用 SMTP 协议发送 email，支持收件人、主题、正文、附件、抄送。"),
        _existing("compress-file", "文件压缩：用 gzip 对文件做无损压缩，输出 .gz 归档。"),
    ]
    out = detect_overlap(new, existing, top_k=2, threshold=0.3)
    assert out, "应返回结果"
    top = out[0]
    assert top["name"] == "send-mail"
    assert top["score"] > 0.3
    assert top["suggest_merge"] is True


def test_unrelated_skill_low():
    """无关 skill → 相似度低（不误报合并）。"""
    new = "发送邮件：通过 SMTP 发送 email。"
    existing = [
        _existing("compress-file", "文件压缩：用 gzip 对文件做无损压缩归档。"),
        _existing("parse-json", "解析 JSON：把 JSON 文本转成结构化对象。"),
    ]
    out = detect_overlap(new, existing, top_k=2, threshold=0.5)
    assert out
    assert all(r["score"] < 0.5 for r in out)
    assert all(r["suggest_merge"] is False for r in out)


def test_top3_returned():
    """返回 top3 且每项含 name/score/suggest_merge。"""
    new = "读取 CSV 表格并做统计分析。"
    existing = [
        _existing(f"skill-{i}", f"技能 {i}：处理数据表格 {i} 行内容，统计汇总。")
        for i in range(6)
    ]
    out = detect_overlap(new, existing, top_k=3)
    assert len(out) == 3
    for r in out:
        assert set(r) == {"name", "score", "suggest_merge"}
        assert isinstance(r["score"], float) and 0.0 <= r["score"] <= 1.0
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True)


def test_tokenize_mixed():
    """中英混排 tokenize：ASCII 词 + CJK 单字 + 双字组均产出。"""
    toks = tokenize("发送 Email 给用户")
    assert "email" in toks
    assert "发" in toks or "送" in toks  # CJK 单字
    assert any(len(t) == 2 and "\u4e00" <= t[0] <= "\u9fff" for t in toks)  # CJK 双字组
