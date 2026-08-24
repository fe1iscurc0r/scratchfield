"""W-04 · skills 规范体检（agentskills.io 对齐）

检查 scratchpad/skills/ 下每个 SKILL.md：
- 文件存在
- frontmatter（--- 起止）存在
- name 字段存在且非空
- description 字段存在且非空

用法: python3 scripts/skill_health_check.py [--fix]
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"


def parse_frontmatter(text: str) -> dict | None:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip("'\"")
    return fm


def scan() -> list[dict]:
    results = []
    if not SKILLS_DIR.exists():
        print(f"目录不存在: {SKILLS_DIR}")
        return results
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("_"):
            continue  # 内部/归档目录（_upstream 等），非独立 skill
        skill_md = skill_dir / "SKILL.md"
        rec = {"dir": skill_dir.name, "ok": True, "issues": []}
        if not skill_md.exists():
            rec["ok"] = False
            rec["issues"].append("缺 SKILL.md")
            results.append(rec)
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        fm = parse_frontmatter(text)
        if fm is None:
            rec["ok"] = False
            rec["issues"].append("无 frontmatter")
        else:
            if not fm.get("name"):
                rec["ok"] = False
                rec["issues"].append("name 缺失")
            if not fm.get("description"):
                rec["ok"] = False
                rec["issues"].append("description 缺失")
        results.append(rec)
    return results


def main() -> int:
    fix = "--fix" in sys.argv
    results = scan()
    total = len(results)
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    rate = len(ok) / total * 100 if total else 100
    print(f"skills 总数: {total} | 合规: {len(ok)} | 不合规: {len(bad)} | 合规率: {rate:.1f}%")
    for r in bad:
        print(f"  [x] {r['dir']}: {'; '.join(r['issues'])}")

    if fix and bad:
        print("\n--fix 模式：从目录名推断 name/description 补写（谨慎，仅补缺失字段）")
        for r in bad:
            skill_dir = SKILLS_DIR / r["dir"]
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                # 尝试找 README.md 作为线索
                readme = skill_dir / "README.md"
                if readme.exists():
                    print(f"  缺 SKILL.md: {r['dir']}（有 README.md，人工确认后再补）")
                else:
                    print(f"  缺 SKILL.md 且无 README: {r['dir']}")
                continue
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            if not text.startswith("---"):
                # 无 frontmatter：加一个基于目录名的最小 frontmatter
                name = r["dir"]
                text = f"---\nname: {name}\ndescription: {name} skill\n---\n\n" + text
                skill_md.write_text(text, encoding="utf-8")
                print(f"  补 frontmatter: {r['dir']}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
