"""Skill 依赖声明（coeffects）解析器。

读取 ``SKILL.md`` frontmatter 的可选 ``coeffects:`` 段，解析依赖规格，
并按依赖是否满足返回三分类：``activate`` / ``deactivate`` / ``neutral``。

原则（对应论文"响应式余效应"）：
- 非侵入：``coeffects:`` 为可选段，不写该段的 skill 行为与现状完全一致。
- 纯增量/旁路：本模块独立可运行，不 hook 现有 skill 加载流程。
- ``packages`` 用 ``importlib.util.find_spec`` 检测，不实际 import（避免副作用）。
- ``services`` 只声明、不 ping（避免启动慢与误报）。

frontmatter 示例::

    ---
    name: my-skill
    coeffects:
      skills:
        - datamol
      packages:
        - rdkit
      services:
        - neo4j
    ---
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# 三分类状态
ACTIVATE = "activate"
DEACTIVATE = "deactivate"
NEUTRAL = "neutral"
CoeffectStatus = str

_SKILL_MD = "SKILL.md"
_FRONTMATTER_RE = re.compile(r"^---\s*$\n(.*?)\n^---\s*$", re.DOTALL | re.MULTILINE)
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")
_NAME_RE = re.compile(r"^name\s*:\s*(.+)$")
_REQUIRED_RE = re.compile(r"^(.*?)\s+required\s*:\s*(true|false|yes|no|1|0)\s*$", re.IGNORECASE)


@dataclass
class CoeffectSpec:
    """从 coeffects 段解析出的依赖规格。

    每个依赖项为 dict：``{"name": str, "required": bool}``。
    ``has_coeffects`` 为 False 表示该 skill 未声明 coeffects 段。
    """

    skills: List[Dict[str, Any]] = field(default_factory=list)
    packages: List[Dict[str, Any]] = field(default_factory=list)
    services: List[Dict[str, Any]] = field(default_factory=list)
    has_coeffects: bool = False

    @classmethod
    def empty(cls) -> "CoeffectSpec":
        return cls()


def resolve_coeffects(skill_dir: str) -> CoeffectSpec:
    """读取 ``skill_dir/SKILL.md`` 的 coeffects 段，返回规格。

    未找到 SKILL.md、无 frontmatter、或未声明 coeffects 段时，
    返回 ``has_coeffects=False`` 的空规格（不影响现有行为）。
    """
    md = Path(skill_dir) / _SKILL_MD
    spec = CoeffectSpec.empty()
    if not md.is_file():
        return spec

    text = md.read_text(encoding="utf-8", errors="ignore")
    fm = _FRONTMATTER_RE.search(text)
    if not fm:
        return spec

    lines = fm.group(1).splitlines()
    idx = _find_coeffects_index(lines)
    if idx is None:
        return spec

    block_lines = _collect_block(lines, idx)
    parsed = _parse_coeffects("\n".join(block_lines))

    spec.skills = parsed.get("skills", [])
    spec.packages = parsed.get("packages", [])
    spec.services = parsed.get("services", [])
    spec.has_coeffects = True
    return spec


def check_satisfied(spec: CoeffectSpec, installed: Set[str]) -> CoeffectStatus:
    """按依赖是否满足返回三分类。

    - 未声明 coeffects → ``neutral``（不影响）。
    - 硬依赖缺失（skills / required 包缺失）→ ``deactivate``。
    - 软依赖缺失（required: false 的包缺失）→ ``neutral``。
    - 依赖全部满足 → ``activate``。
    - services 仅声明、不参与判定。
    """
    if not spec.has_coeffects:
        return NEUTRAL

    missing_hard: List[str] = []
    missing_soft: List[str] = []
    for entry in spec.skills:
        if _satisfied_entry(entry, installed, kind="skill"):
            continue
        (missing_hard if entry.get("required", True) else missing_soft).append(entry.get("name"))

    for entry in spec.packages:
        if _satisfied_entry(entry, installed, kind="package"):
            continue
        (missing_hard if entry.get("required", True) else missing_soft).append(entry.get("name"))

    if missing_hard:
        return DEACTIVATE
    if missing_soft:
        return NEUTRAL
    return ACTIVATE


# ----------------------------------------------------------------- internal


def _find_coeffects_index(lines: List[str]) -> Optional[int]:
    """返回 frontmatter 中顶层 ``coeffects:`` 所在行号，无则 None。"""
    for j, ln in enumerate(lines):
        if ln.strip() == "coeffects:" and (len(ln) - len(ln.lstrip())) == 0:
            return j
    return None


def _collect_block(lines: List[str], idx: int) -> List[str]:
    """收集 ``coeffects:`` 之后、下一个顶层键之前的缩进行。"""
    block: List[str] = []
    for ln in lines[idx + 1:]:
        if not ln.strip():
            continue
        if (len(ln) - len(ln.lstrip())) == 0:
            break
        block.append(ln)
    return block


def _parse_coeffects(block: str) -> Dict[str, List[Dict[str, Any]]]:
    """把 coeffects 块解析为 {skills|packages|services: [{name, required}]}。"""
    out: Dict[str, List[Dict[str, Any]]] = {"skills": [], "packages": [], "services": []}
    current_key: Optional[str] = None
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        content = line.strip()
        if content.endswith(":") and not content.startswith("-"):
            current_key = content.rstrip(":").strip()
            if current_key not in out:
                out[current_key] = []
            continue
        if content.startswith("-"):
            rest = content[1:].strip()
            if current_key in out:
                out[current_key].append(_entry(rest))
            continue
        # 续行属性（如 "- name: rdkit" 后的 "  required: false"）
        pm = _KEY_RE.match(content)
        if pm and current_key in out and out[current_key]:
            last = out[current_key][-1]
            if isinstance(last, dict):
                last[pm.group(1)] = _scalar(pm.group(2))
    return out


def _entry(text: str) -> Dict[str, Any]:
    """把一个列表项规范化为 {"name": str, "required": bool}。

    支持 ``- rdkit``、``- name: rdkit``、``- rdkit required: false``。
    """
    required = True
    m = _REQUIRED_RE.match(text)
    if m:
        text = m.group(1).strip()
        required = _bool(m.group(2))
    nm = _NAME_RE.match(text)
    if nm:
        return {"name": nm.group(1).strip(), "required": required}
    return {"name": text, "required": required}


def _satisfied_entry(entry: Dict[str, Any], installed: Set[str], kind: str) -> bool:
    name = entry.get("name")
    if not name:
        return True
    if name in installed:
        return True
    if kind == "package":
        return _find_spec(name) is not None
    return False


def _find_spec(name: str) -> Any:
    """用 ``importlib.util.find_spec`` 检测包，不实际 import。"""
    try:
        return importlib.util.find_spec(name)
    except (ImportError, ValueError, ModuleNotFoundError):
        return None


def _bool(value: str) -> bool:
    return str(value).strip().lower() in ("true", "yes", "1")


def _scalar(value: str) -> Any:
    v = value.strip()
    if v == "":
        return True
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    if v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    return v