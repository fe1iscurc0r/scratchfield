"""Skills 技能加载循环（卷124 W124-05）。

Hermes 的 skills 模式落到陆墨：**技能清单 → 按意图检索 → 读 SKILL.md → 注入上下文 → 执行 → 回写**。

```
用户消息 ──┬─ 关键词匹配技能库（frontmatter: name/description/trigger + 正文）
           ├─ 命中 Top-K（默认 2）→ 读 SKILL.md 正文（按 token 预算截断）
           ├─ 未命中 → **零注入**（省 token，不硬塞）
           └─ 注入 system 层（并入 messages[0]，沿用卷121 的 relay 教训）
                    ↓
            模型按技能规范执行 → 回写 `lumo.skill.invoked` 事件（哪技能/命中分/注入长度）
```

技能库来源（按顺序合并，同名以先出现的为准）：

1. `<user_data>/skills/public/*/SKILL.md` —— 用户导入/安装的技能
2. `<user_data>/skills/cache/*/SKILL.md` —— 技能市场缓存
3. `apiserver/skills_templates/*/SKILL.md` —— 内置模板（存在时）
4. `skills.extra_dirs` 配置的额外目录

frontmatter 校验（对齐 dsh-std 的静态 manifest 预检思路）：`name` / `description` 必填，
非法技能**拒绝导入**（装上就能查元数据，不用跑才知道）。
角色技能白名单走 W124-01 的 Scope（`role.skills`），过滤在同一处。
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
#: 关键词：ASCII 词（长度≥4）/ 中文词（长度≥2）
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{3,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

MAX_BODY_CHARS = 4000


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "skills", None)
    except Exception:  # noqa: BLE001
        return None


def enabled() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "enabled", True)) if cfg is not None else True


def max_skills() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "max_skills", 2) or 2) if cfg is not None else 2


def threshold() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "threshold", 2) or 2) if cfg is not None else 2


def max_chars_per_skill() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "max_chars_per_skill", 1200) or 1200) if cfg is not None else 1200


def search_dirs() -> List[Path]:
    """技能库目录（按优先级）。"""
    dirs: List[Path] = []
    try:
        from system.config import get_data_dir

        base = Path(get_data_dir()) / "skills"
        dirs += [base / "public", base / "cache"]
    except Exception:  # noqa: BLE001
        pass
    dirs.append(Path(__file__).resolve().parent / "skills_templates")
    cfg = _cfg()
    for extra in (getattr(cfg, "extra_dirs", None) or []):
        text = str(extra).strip()
        if text:
            dirs.append(Path(text).expanduser())
    return dirs


# ---------------------------------------------------------------------------
# 解析与校验
# ---------------------------------------------------------------------------


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """解析 `---` frontmatter（键值行，支持 `key: value` 与 `key: [a, b]`）。"""
    if not text:
        return {}, ""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: Dict[str, Any] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",")]
            meta[key.strip()] = [i for i in items if i]
        else:
            meta[key.strip()] = value
    return meta, text[match.end():]


def validate_frontmatter(meta: Dict[str, Any]) -> Tuple[bool, str]:
    """静态预检：name / description 必填且长度合理。"""
    name = str(meta.get("name") or "").strip()
    description = str(meta.get("description") or "").strip()
    if not name:
        return False, "缺少 name"
    if not description:
        return False, "缺少 description"
    if len(name) > 120:
        return False, "name 过长（>120）"
    if len(description) < 10:
        return False, "description 过短（<10）"
    return True, ""


def validate_skill_file(path: Path) -> Tuple[bool, str]:
    """校验一个 SKILL.md 文件（供导入接口复用）。"""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, "文件不存在"
    except Exception as e:  # noqa: BLE001
        return False, f"读取失败: {e}"
    meta, _body = parse_frontmatter(text)
    return validate_frontmatter(meta)


# ---------------------------------------------------------------------------
# 技能库
# ---------------------------------------------------------------------------


class Skill:
    def __init__(self, name: str, description: str, body: str, path: Path,
                 triggers: List[str] | None = None) -> None:
        self.name = name
        self.description = description
        self.body = body
        self.path = path
        self.triggers = list(triggers or [])
        self.keywords = _keywords(name, description, self.triggers)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "description": self.description[:200],
                "path": str(self.path), "triggers": self.triggers}


def _keywords(name: str, description: str, triggers: Iterable[str]) -> List[str]:
    """抽取匹配关键词：ASCII 词 + 中文词（英文/中文都能命中）。"""
    words: List[str] = []
    for source in [str(name or ""), *[str(t) for t in triggers], str(description or "")]:
        words += [w.lower() for w in _ASCII_WORD_RE.findall(source)]
        words += _CJK_TOKEN_RE.findall(source)
    seen: Dict[str, None] = {}
    for word in words:
        if len(word) >= 2:
            seen.setdefault(word, None)
    return list(seen)[:80]


def load_skill(skill_dir: Path) -> Skill | None:
    path = Path(skill_dir)
    file = path / "SKILL.md" if path.is_dir() else path
    if not file.is_file():
        return None
    try:
        text = file.read_text(encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logger.debug("[skill_loader] 读取技能失败 %s: %s", file, e)
        return None
    meta, body = parse_frontmatter(text)
    ok, reason = validate_frontmatter(meta)
    if not ok:
        logger.warning("[skill_loader] 跳过非法技能 %s：%s", file, reason)
        return None
    triggers = meta.get("trigger") or meta.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [t.strip() for t in re.split(r"[,，;；]", triggers) if t.strip()]
    return Skill(
        name=str(meta.get("name")), description=str(meta.get("description")),
        body=body.strip()[:MAX_BODY_CHARS], path=file, triggers=list(triggers),
    )


def load_library(*, dirs: List[Path] | None = None, db_path: Any = None) -> List[Skill]:
    """扫描技能库（同名以先出现的目录为准）。"""
    skills: List[Skill] = []
    seen: set[str] = set()
    for base in (dirs if dirs is not None else search_dirs()):
        try:
            if not Path(base).is_dir():
                continue
            for child in sorted(Path(base).iterdir()):
                if not child.is_dir():
                    continue
                skill = load_skill(child)
                if skill and skill.name not in seen:
                    seen.add(skill.name)
                    skills.append(skill)
        except Exception as e:  # noqa: BLE001 - 单个目录异常不影响其它目录
            logger.debug("[skill_loader] 扫描目录失败 %s: %s", base, e)
    return skills


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------


def match_skills(
    text: str, *, skills: List[Skill] | None = None, limit: int | None = None,
    min_score: int | None = None, role: str | None = None,
) -> List[Tuple[Skill, int]]:
    """按关键词命中打分，返回 `[(skill, score)]`（分数降序，未达阈值不返回）。"""
    if not enabled() or not str(text or "").strip():
        return []
    library = skills if skills is not None else load_library()
    message = str(text)
    lowered = message.lower()
    scored: List[Tuple[Skill, int]] = []
    for skill in library:
        if not _skill_visible(skill.name, role=role):
            continue
        score = 0
        for keyword in skill.keywords:
            if _CJK_RE.search(keyword):
                if keyword in message:
                    score += 2  # 中文命中通常更精确，权重稍高
            elif keyword in lowered:
                score += 1
        if str(skill.name).lower() in lowered:
            score += 3
        if score > 0:
            scored.append((skill, score))
    scored.sort(key=lambda item: item[1], reverse=True)
    cutoff = threshold() if min_score is None else int(min_score)
    cap = max_skills() if limit is None else int(limit)
    return [item for item in scored if item[1] >= cutoff][: max(1, cap)]


def _skill_visible(skill_name: str, *, role: str | None = None) -> bool:
    try:
        from mcpserver import scope as scope_mod

        return scope_mod.is_skill_visible(skill_name, role=role)
    except Exception:  # noqa: BLE001 - Scope 不可用则不额外限制
        return True


def build_skill_context(
    text: str, *, session_id: str = "", role: str | None = None,
    skills: List[Skill] | None = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """按意图组装技能上下文。

    Returns:
        (注入文本, 命中记录列表)；未命中返回 ("", [])——**零注入**。
    """
    hits = match_skills(text, skills=skills, role=role)
    if not hits:
        return "", []
    parts: List[str] = ["〔可用技能〕（按当前意图命中，按规范执行；与本轮无关可忽略）"]
    records: List[Dict[str, Any]] = []
    for skill, score in hits:
        body = skill.body[: max_chars_per_skill()]
        if len(skill.body) > len(body):
            body += "\n…（技能正文按预算截断）"
        parts.append(f"### 技能 {skill.name}（命中分 {score}）\n{body}")
        records.append({"skill": skill.name, "score": score, "injected_chars": len(body),
                        "path": str(skill.path), "session_id": session_id})
    return "\n\n".join(parts), records


def record_usage(records: List[Dict[str, Any]]) -> None:
    """回写技能使用记录（事件总线，失败静默）。"""
    for record in records or []:
        try:
            from apiserver.event_bus import get_bus

            get_bus().emit("lumo.skill.invoked", {**record, "ts": time.time()})
        except Exception as e:  # noqa: BLE001 - 回写失败不影响对话
            logger.debug("[skill_loader] 技能使用回写失败: %s", e)
            break


def library_summary(*, role: str | None = None) -> Dict[str, Any]:
    """调试/接口用：技能库概览（含非法技能数与原因）。"""
    skills = load_library()
    invalid: List[str] = []
    for base in search_dirs():
        try:
            if not Path(base).is_dir():
                continue
            for child in sorted(Path(base).iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file() and load_skill(child) is None:
                    invalid.append(str(child / "SKILL.md"))
        except Exception:  # noqa: BLE001
            continue
    return {
        "enabled": enabled(),
        "dirs": [str(d) for d in search_dirs()],
        "count": len(skills),
        "skills": [s.to_dict() for s in skills],
        "visible": [s.name for s in skills if _skill_visible(s.name, role=role)],
        "invalid": invalid,
        "budget": {"max_skills": max_skills(), "threshold": threshold(),
                   "max_chars_per_skill": max_chars_per_skill()},
    }
