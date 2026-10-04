"""BibTeX 引用管理（SPEC-02 Phase 4 任务 4.2）。

纯 Python 实现（不依赖 bibtexparser）：
- 条目按 @type{key, ...} 块存取于 references.bib
- 支持按关键词检索、生成引用标号与参考文献节
- 库文件缺省 %APPDATA%/Lumo/writing/references.bib，LUMO_WRITING_DIR 可覆盖
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,(.*?)\n\}", re.DOTALL)
# 字段值取到第一个 }（本库字段不含嵌套花括号）；跨行贪婪会把后续字段吞进 title。
_FIELD_RE = re.compile(r"^\s*(\w+)\s*=\s*\{([^}]*)\}\s*,?\s*$", re.MULTILINE)


def default_bib_path() -> Path:
    base = os.environ.get("LUMO_WRITING_DIR")
    if base:
        d = Path(base)
    else:
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Lumo" / "writing"
    d.mkdir(parents=True, exist_ok=True)
    return d / "references.bib"


def _entry_to_text(entry_type: str, key: str, fields: dict) -> str:
    lines = [f"@{entry_type}{{{key},"]
    for k, v in fields.items():
        lines.append(f"  {k} = {{{v}}},")
    lines.append("}")
    return "\n".join(lines)


def add_entry(key: str, title: str, authors: str, year, journal: str = "",
              doi: str = "", entry_type: str = "article",
              bib_path: Path | None = None) -> dict:
    """追加一条文献（key 重复则拒绝，避免覆盖已有条目）。"""
    path = Path(bib_path) if bib_path else default_bib_path()
    entries = load_entries(path)
    if key in entries:
        return {"success": False, "error": f"key 已存在: {key}"}
    fields = {"title": title, "author": authors, "year": str(year)}
    if journal:
        fields["journal"] = journal
    if doi:
        fields["doi"] = doi
    text = _entry_to_text(entry_type, key, fields)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text + "\n\n")
    return {"success": True, "key": key, "bib_path": str(path)}


def load_entries(bib_path: Path | None = None) -> dict[str, dict]:
    """解析 bib 文件为 {key: {type, **fields}}。文件不存在返回空。"""
    path = Path(bib_path) if bib_path else default_bib_path()
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for m in _ENTRY_RE.finditer(text):
        etype, key, body = m.group(1), m.group(2), m.group(3)
        fields = {"_type": etype}
        for fm in _FIELD_RE.finditer(body):
            fields[fm.group(1).lower()] = fm.group(2).strip()
        out[key] = fields
    return out


def find_entries(keyword: str, bib_path: Path | None = None) -> list[dict]:
    """按关键词（标题/作者/期刊任一命中，大小写不敏感）检索。"""
    kw = keyword.lower()
    hits = []
    for key, f in load_entries(bib_path).items():
        hay = " ".join(str(v) for v in f.values()).lower()
        if kw in hay:
            hits.append({"key": key, **f})
    return hits


def cite_section(keys: list[str], bib_path: Path | None = None) -> dict:
    """生成编号引用映射与 Markdown 参考文献节。"""
    entries = load_entries(bib_path)
    lines, marks, missing = [], [], []
    for i, key in enumerate(keys, 1):
        f = entries.get(key)
        if not f:
            missing.append(key)
            continue
        marks.append(f"{key} -> [{i}]")
        authors = f.get("author", "").replace(" and ", ", ")
        title = f.get("title", "")
        journal = f.get("journal", "")
        year = f.get("year", "")
        doi = f.get("doi", "")
        line = f"{i}. {authors}. *{title}*. {journal} ({year})."
        if doi:
            line += f" doi:{doi}"
        lines.append(line)
    md = "## References\n\n" + "\n".join(lines) if lines else "## References\n"
    return {"success": not missing and bool(keys), "marks": marks,
            "missing": missing, "markdown": md}


def seed_academic_refs(bib_path: Path | None = None) -> dict:
    """注入 academic 16 项中自带引用信息的条目（幂等：已存在则跳过）。"""
    seeds = [
        ("thermo2024", "article",
         "Thermo: Chemical properties component of Chemical Engineering Design Library (ChEDL)",
         "Caleb Bell and Contributors", "2024",
         "https://github.com/CalebBell/thermo", ""),
        ("witte2020tespy", "article",
         "TESPy: Thermal Engineering Systems in Python",
         "Francesco Witte and Ilja Tuschy", "2020",
         "Journal of Open Source Software", "10.21105/joss.02178"),
        ("xiao2023slices", "article",
         "An invertible, invariant crystal representation for inverse design of solid-state materials using generative deep learning",
         "Hang Xiao and Rong Li and Xiaoyang Shi and Yan Chen and Lei Wang", "2023",
         "Nature Communications", "10.1038/s41467-023-42870-7"),
        ("fredericks2021pyxtal", "article",
         "PyXtal: A Python library for crystal structure generation and symmetry analysis",
         "Scott Fredericks and Kevin Parrish and Dean Sayre and Qiang Zhu", "2021",
         "Computer Physics Communications", "10.1016/j.cpc.2020.107810"),
        ("otis2017pycalphad", "article",
         "pycalphad: CALPHAD-based Computational Thermodynamics in Python",
         "Richard Otis and Zi-Kui Liu", "2017",
         "Journal of Open Research Software", "10.5334/jors.140"),
    ]
    added, skipped = [], []
    for key, etype, title, authors, year, journal, doi in seeds:
        r = add_entry(key, title, authors, year, journal, doi, etype, bib_path)
        (added if r["success"] else skipped).append(key)
    return {"success": True, "added": added, "skipped": skipped}
