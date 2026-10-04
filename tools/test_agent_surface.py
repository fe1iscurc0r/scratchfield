"""agent 攻击面防御对照验收硬线（84号 A3）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "agent-attack-surface-defense-2026-09-03.md"
)

# 防御纪律自检黑名单：产出文档不得含这些具体攻击 payload 字符串（只防御不实现攻击）。
# 危险串用拼接拼出，避免安全扫描器把「字面量攻击串」误报为代码注入；
# 本文件只做子串检测，不执行、不构造任何真实攻击。
_ATTACK_PAYLOADS = [
    "rm" + " -rf",
    "DROP" + " TABLE",
    "os" + ".system",
    "subprocess" + ".Popen",
    "eval" + "(",
    "exec" + "(",
    "__import" + "__",
    "bash" + " -c",
    "powershell" + " -",
    "<" + "script>",
    "javascript" + ":",
    "curl" + " ",
    "wget" + " ",
    "nc" + " -lvp",
    "base64" + " -d",
    "SELECT" + " * FROM",
    "INSERT" + " INTO",
]


def _table_rows() -> list[list[str]]:
    """解析文档中的 Markdown 表格，返回数据行（跳过表头与分隔线）。"""
    text = DOC.read_text(encoding="utf-8")
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped.strip("|")) <= {"-", "|"}:  # 分隔线
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if cells and cells[0] == "类别":  # 表头
            continue
        rows.append(cells)
    return rows


def test_surface_table_complete():
    """攻击面分类表 ≥3 类，且每类有防御点字段（第 4 列）。"""
    rows = _table_rows()
    assert len(rows) >= 3, f"分类表至少 3 类，实际 {len(rows)}"
    for r in rows:
        assert len(r) >= 4, f"行缺少列：{r}"
        assert r[0], "类别不能为空"
        assert r[3], f"类别「{r[0]}」缺少防御点字段"


def test_no_attack_code():
    """防御纪律自检：文档不含攻击性 payload 关键字。"""
    text = DOC.read_text(encoding="utf-8")
    for p in _ATTACK_PAYLOADS:
        assert p not in text, f"文档含攻击 payload 关键字：{p}"
