#!/usr/bin/env python3
"""skill 分发管线原型（K02）。

把 scratchpad `skills/` 扁平目录固化为可分发资产：
- index   生成 skills/INDEX.md（人读）+ skills/index.json（机器读）
- check   frontmatter 门禁（name/description/license）+ 版本/许可聚合
- install 把选定 skill 复制/软链到 agent 约定目录

参考 TanStack/cli 的 skill_spec.md + .agents/.claude/.cursor 安装协议。
仅用标准库，无第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

FIELD_RE = {
    "name": re.compile(r"^name:\s*(.+?)\s*$"),
    "description": re.compile(r"^description:\s*(.+?)\s*$"),
    "license": re.compile(r"^license:\s*(.+?)\s*$"),
    "version": re.compile(r"^version:\s*(.+?)\s*$"),
}


def parse_frontmatter(text: str) -> dict[str, str]:
    """极简 YAML frontmatter 解析：取 --- ... --- 块内的顶层 key: value。"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end]
    out: dict[str, str] = {}
    in_metadata = False
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("metadata:"):
            in_metadata = True
            continue
        if in_metadata and not line.startswith(" ") and stripped:
            in_metadata = False
        for key, pat in FIELD_RE.items():
            m = pat.match(stripped)
            if m:
                out[key] = m.group(1).strip()
        # metadata 块内的 version 顶到顶层
        if in_metadata:
            m = FIELD_RE["version"].match(stripped)
            if m:
                out["version"] = m.group(1).strip()
    return out


def collect(skills_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        name = skill_md.parent.name
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
        rows.append(
            {
                "name": fm.get("name") or name,
                "dir": name,
                "description": fm.get("description", ""),
                "license": fm.get("license", ""),
                "version": fm.get("version", "unknown"),
            }
        )
    return rows


def cmd_index(skills_dir: Path) -> int:
    rows = collect(skills_dir)
    (skills_dir / "index.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# skills 索引（skill_spec 风格）", "", f"共 {len(rows)} 个 skill。", ""]
    lines += ["| name | version | license | description |", "|------|---------|---------|-------------|"]
    for r in rows:
        desc = r["description"].replace("\n", " ").replace("|", "/")[:80]
        lines.append(f"| {r['name']} | {r['version']} | {r['license'] or '-'} | {desc} |")
    (skills_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"index: 写了 {skills_dir}/INDEX.md 与 index.json（{len(rows)} 个 skill）")
    return 0


def cmd_check(skills_dir: Path) -> int:
    rows = collect(skills_dir)
    missing = {"name": 0, "description": 0, "license": 0}
    licenses: dict[str, int] = {}
    versions: set[str] = set()
    for r in rows:
        for k in missing:
            if not r[k]:
                missing[k] += 1
                print(f"  FAIL {r['dir']}: 缺 {k}")
        if r["license"]:
            licenses[r["license"]] = licenses.get(r["license"], 0) + 1
        versions.add(r["version"])
    print(f"check: {len(rows)} skill；缺字段 {missing}；版本集 {sorted(versions)[:10]}…")
    print("许可分布:", json.dumps(licenses, ensure_ascii=False))
    return 0


def cmd_install(skills_dir: Path, names: list[str], to: Path, link: bool) -> int:
    to.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name in names:
        src = skills_dir / name
        dst = to / name
        if not (src / "SKILL.md").exists():
            print(f"  SKIP {name}: 不存在 SKILL.md")
            continue
        if dst.exists():
            print(f"  SKIP {name}: 目标已存在（--force 可覆盖）")
            continue
        if link:
            try:
                dst.symlink_to(src, target_is_directory=True)
            except OSError:
                shutil.copytree(src, dst)
        else:
            shutil.copytree(src, dst)
        print(f"  INSTALL {name} -> {dst}")
        ok += 1
    print(f"install: {ok}/{len(names)} 完成，落点 {to}")
    return 0


def main(argv: list[str]) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--skills-dir", default="skills", help="skill 根目录（默认 skills）")

    p = argparse.ArgumentParser(description="skill 分发管线原型", parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index", help="生成 INDEX.md + index.json", parents=[common])
    sub.add_parser("check", help="frontmatter 门禁", parents=[common])
    ip = sub.add_parser("install", help="安装到 agent 目录", parents=[common])
    ip.add_argument("names", nargs="+", help="skill 名（目录名）")
    ip.add_argument("--to", required=True, help="目标 agent 目录，如 .agents/skills")
    ip.add_argument("--link", action="store_true", help="优先软链而非复制")
    args = p.parse_args(argv)

    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir():
        print(f"错误：{skills_dir} 不是目录", file=sys.stderr)
        return 2
    if args.cmd == "index":
        return cmd_index(skills_dir)
    if args.cmd == "check":
        return cmd_check(skills_dir)
    if args.cmd == "install":
        return cmd_install(skills_dir, args.names, Path(args.to), args.link)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
