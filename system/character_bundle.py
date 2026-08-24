#!/usr/bin/env python3
"""角色模板一层装配器。

将 characters/<name>/ 下的基础人格提示和角色自带技能合成为统一的第一层内容。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from system.config import CHARACTERS_DIR, load_character, strip_prompt_comment_lines

logger = logging.getLogger(__name__)

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _read_text(path: Path, max_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = strip_prompt_comment_lines(path.read_text(encoding="utf-8")).strip()
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[已截断]"


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = _FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        logger.warning(f"[CharacterBundle] 解析 frontmatter 失败: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def strip_frontmatter(text: str) -> str:
    match = _FRONTMATTER_PATTERN.match(text)
    if match:
        text = text[match.end():]
    return text.strip()


def _strip_leading_heading(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        return "\n".join(lines[1:]).lstrip()
    return text


def _iter_character_skill_files(character_dir: Path) -> list[Path]:
    skills_dir = character_dir / "skills"
    if not skills_dir.exists():
        return []
    return sorted(path for path in skills_dir.rglob("SKILL.md") if path.is_file())


def load_character_prompt_text(character_template: str | None, max_chars: int = 12000) -> str:
    if not character_template:
        return ""

    char_meta = load_character(character_template)
    prompt_file = char_meta.get("prompt_file") or "conversation_style_prompt.txt"
    prompt_path = CHARACTERS_DIR / character_template / prompt_file
    return _read_text(prompt_path, max_chars=max_chars)


def load_character_skill_sections(
    character_template: str | None,
    max_chars_per_skill: int = 8000,
) -> list[dict[str, str]]:
    if not character_template:
        return []

    character_dir = CHARACTERS_DIR / character_template
    sections: list[dict[str, str]] = []

    for skill_file in _iter_character_skill_files(character_dir):
        raw_text = _read_text(skill_file, max_chars=max_chars_per_skill)
        if not raw_text:
            continue

        metadata = _parse_frontmatter(raw_text)
        title = str(metadata.get("name") or skill_file.parent.name).strip() or skill_file.parent.name
        description = str(metadata.get("description") or "").strip()
        body = _strip_leading_heading(strip_frontmatter(raw_text))
        if not body:
            continue

        sections.append({
            "title": title,
            "description": description,
            "content": body,
        })

    return sections


def build_legacy_character_identity(
    character_template: str | None,
    *,
    prompt_max_chars: int = 12000,
) -> str:
    """构建旧版只含人格模板的 IDENTITY 内容，用于兼容升级判断。"""
    if not character_template:
        return ""

    prompt_text = load_character_prompt_text(character_template, max_chars=prompt_max_chars)
    if not prompt_text:
        return ""

    return (
        f"# 人格模板：{character_template}\n\n"
        "以下内容从 characters 模板初始化，用作该干员的人格基底。\n"
        "后续个性化发展请写入 SOUL.md 等实例文件，不要改回模板源。\n\n"
        f"{prompt_text}\n"
    )


def is_legacy_character_identity(
    content: str,
    character_template: str | None,
    *,
    prompt_max_chars: int = 12000,
) -> bool:
    legacy = build_legacy_character_identity(character_template, prompt_max_chars=prompt_max_chars)
    if not legacy or not content:
        return False
    return content.strip() == legacy.strip()


def build_character_identity_bundle(
    character_template: str | None,
    *,
    prompt_max_chars: int = 12000,
    skill_max_chars: int = 8000,
) -> str:
    """构建角色第一层 bundle。

    返回可直接写入 IDENTITY.md 或作为运行时 system prompt 基底的文本。
    """
    if not character_template:
        return ""

    prompt_text = load_character_prompt_text(character_template, max_chars=prompt_max_chars)
    skill_sections = load_character_skill_sections(character_template, max_chars_per_skill=skill_max_chars)

    sections: list[str] = []
    if prompt_text:
        sections.append("## 角色人格模板\n\n" + prompt_text)

    if skill_sections:
        skill_blocks = [
            "## 角色自带技能\n\n"
            "以下技能属于该角色模板的一部分，会随角色一同注入，不作为可选公共技能。"
        ]
        for section in skill_sections:
            parts = [f"### {section['title']}"]
            if section["description"]:
                parts.append(section["description"])
            parts.append(section["content"])
            skill_blocks.append("\n\n".join(parts))
        sections.append("\n\n".join(skill_blocks))

    if not sections:
        return ""

    return (
        f"# 人格模板：{character_template}\n\n"
        "以下内容从 characters 模板初始化，用作该干员的人格基底。\n"
        "后续个性化发展请写入 SOUL.md、记忆和记事本等实例文件，不要改回模板源。\n\n"
        + "\n\n".join(sections).strip()
        + "\n"
    )
