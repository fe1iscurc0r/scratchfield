"""领域包（Domain Pack）加载器。

扫描仓库根 `domains/*/pack.yaml`，把「学科/职业工作流配置」变成声明式数据，
使核心代码无需出现任何 `if domain == "law"` 分支即可新增领域。

设计要点
--------
- **加载即校验，失败降级为警告**：单个包 yaml 坏掉不得炸掉 apiserver 启动，
  只记 warning 并跳过该包。
- **默认包 `default` 必须存在且行为等价于改造前**：这是回归红线，加载器会
  在 `default` 缺失时给出明确警告（但不抛异常）。
- **零新依赖**：只用已有 `pyyaml`。

pack.yaml schema（完整说明见 docs/领域包指南.md）
------------------------------------------------
```yaml
name: law                       # 必填，须与目录名一致
label: 法学                      # 必填，界面展示名
description: 法学判例与法规工作流   # 可选
eln:                            # 可选，ELN 表单字段
  fields:                       # 有序字段列表，顺序即表单展示顺序
    - key: 当事人
      type: text                # text | textarea | list | date
      label: 当事人
      required: false
papers:                         # 可选，论文/文献主键扩展
  id_fields: [flk_id, case_no]  # default: [doi, arxiv_id]
source_presets:                 # 可选，来源预设（版权标注用）
  - key: pkulaw
    label: 北大法宝
    license_note: 个人订阅使用，勿再分发
tagging:                        # 可选，打标蓝图（卷164 消费）
  questions:
    - key: 案由分类
      type: choice              # boolean | choice | score
      options: [合同纠纷, 侵权责任纠纷]
```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# `domains/` 位于仓库根，本文件在 apiserver/ 下，故上溯一层。
_REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = _REPO_ROOT / "domains"

DEFAULT_PACK_NAME = "default"

# 改造前 eln.py 的硬编码字段（顺序即模板展示顺序）。
# 默认包 pack.yaml 一旦缺失或坏掉，回退到这份快照，保证行为不回归。
_LEGACY_ELN_FIELDS = [
    "date",
    "topic",
    "status",
    "purpose",
    "reagents",
    "conditions",
    "results",
    "attachments",
    "conclusion",
    "references",
]

# 改造前 papers.py 的主键字段。
_LEGACY_ID_FIELDS = ["doi", "arxiv_id"]

_ALLOWED_ELN_FIELD_TYPES = {"text", "textarea", "list", "date"}
_ALLOWED_QUESTION_TYPES = {"boolean", "choice", "score"}


class DomainPackError(Exception):
    """领域包校验失败。仅用于内部，加载器会把它降级成 warning。"""


@dataclass
class ElnField:
    key: str
    type: str = "text"
    label: str = ""
    required: bool = False
    #: 是否在前端表单中渲染。改造前 default 的前端表单不渲染 `attachments`
    #: （它只出现在导出 Markdown 的 frontmatter 里），故 default 包把它标 false。
    #: 后端 frontmatter 生成不受此开关影响，始终包含全部字段。
    show_in_form: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "type": self.type,
            "label": self.label or self.key,
            "required": self.required,
            "show_in_form": self.show_in_form,
        }


@dataclass
class TaggingQuestion:
    key: str
    type: str = "choice"
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "type": self.type, "options": list(self.options)}


@dataclass
class SourcePreset:
    key: str
    label: str = ""
    license_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label or self.key,
            "license_note": self.license_note,
        }


@dataclass
class DomainPack:
    name: str
    label: str
    description: str = ""
    eln_fields: list[ElnField] = field(default_factory=list)
    id_fields: list[str] = field(default_factory=lambda: list(_LEGACY_ID_FIELDS))
    source_presets: list[SourcePreset] = field(default_factory=list)
    tagging_questions: list[TaggingQuestion] = field(default_factory=list)
    #: 包目录，供模板/导入器等相对资源定位（如 eln_templates/、importers/）。
    path: Path | None = None
    #: pack.yaml 原文，便于调试与文档生成。
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def eln_field_keys(self) -> list[str]:
        return [f.key for f in self.eln_fields]

    @property
    def form_eln_fields(self) -> list[ElnField]:
        """前端表单需要渲染的字段（`show_in_form=True`）。"""
        return [f for f in self.eln_fields if f.show_in_form]

    def to_dict(self) -> dict[str, Any]:
        """序列化为 `GET /api/domains` 的响应元素。"""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "eln": {
                "fields": [f.to_dict() for f in self.eln_fields],
                "form_fields": [f.to_dict() for f in self.form_eln_fields],
            },
            "papers": {"id_fields": list(self.id_fields)},
            "source_presets": [p.to_dict() for p in self.source_presets],
            "tagging": {"questions": [q.to_dict() for q in self.tagging_questions]},
        }


def _as_str_list(value: Any, ctx: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DomainPackError(f"{ctx} 应为列表，实际为 {type(value).__name__}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DomainPackError(f"{ctx} 的元素应为非空字符串，实际为 {item!r}")
        out.append(item.strip())
    return out


def _parse_eln(raw: Any) -> list[ElnField]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise DomainPackError("eln 应为映射")
    fields_raw = raw.get("fields")
    if fields_raw is None:
        return []
    if not isinstance(fields_raw, list):
        raise DomainPackError("eln.fields 应为列表")

    out: list[ElnField] = []
    for i, item in enumerate(fields_raw):
        if isinstance(item, str):
            # 简写：- date
            out.append(ElnField(key=item.strip(), type="text"))
            continue
        if not isinstance(item, dict):
            raise DomainPackError(f"eln.fields[{i}] 应为字符串或映射")
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DomainPackError(f"eln.fields[{i}] 缺 key")
        ftype = str(item.get("type") or "text").strip()
        if ftype not in _ALLOWED_ELN_FIELD_TYPES:
            raise DomainPackError(
                f"eln.fields[{i}] type={ftype!r} 不在 {sorted(_ALLOWED_ELN_FIELD_TYPES)}"
            )
        label = item.get("label")
        out.append(
            ElnField(
                key=key.strip(),
                type=ftype,
                label=str(label).strip() if label else "",
                required=bool(item.get("required", False)),
                show_in_form=bool(item.get("show_in_form", True)),
            )
        )
    return out


def _parse_source_presets(raw: Any) -> list[SourcePreset]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DomainPackError("source_presets 应为列表")
    out: list[SourcePreset] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DomainPackError(f"source_presets[{i}] 应为映射")
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DomainPackError(f"source_presets[{i}] 缺 key")
        out.append(
            SourcePreset(
                key=key.strip(),
                label=str(item.get("label") or "").strip(),
                license_note=str(item.get("license_note") or "").strip(),
            )
        )
    return out


def _parse_tagging(raw: Any) -> list[TaggingQuestion]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise DomainPackError("tagging 应为映射")
    qs = raw.get("questions")
    if qs is None:
        return []
    if not isinstance(qs, list):
        raise DomainPackError("tagging.questions 应为列表")
    out: list[TaggingQuestion] = []
    for i, item in enumerate(qs):
        if not isinstance(item, dict):
            raise DomainPackError(f"tagging.questions[{i}] 应为映射")
        key = item.get("key")
        if not isinstance(key, str) or not key.strip():
            raise DomainPackError(f"tagging.questions[{i}] 缺 key")
        qtype = str(item.get("type") or "choice").strip()
        if qtype not in _ALLOWED_QUESTION_TYPES:
            raise DomainPackError(
                f"tagging.questions[{i}] type={qtype!r} 不在 {sorted(_ALLOWED_QUESTION_TYPES)}"
            )
        options = _as_str_list(item.get("options"), f"tagging.questions[{i}].options")
        if qtype == "choice" and not options:
            raise DomainPackError(f"tagging.questions[{i}] type=choice 必须有 options")
        out.append(TaggingQuestion(key=key.strip(), type=qtype, options=options))
    return out


def load_pack(pack_dir: Path) -> DomainPack:
    """从单个包目录加载 pack.yaml。校验失败抛 DomainPackError。"""
    manifest = pack_dir / "pack.yaml"
    if not manifest.is_file():
        raise DomainPackError(f"缺少 pack.yaml: {manifest}")

    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise DomainPackError(f"pack.yaml 解析失败: {exc}") from exc

    if not isinstance(raw, dict):
        raise DomainPackError("pack.yaml 顶层应为映射")

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise DomainPackError("缺 name")
    name = name.strip()
    if name != pack_dir.name:
        raise DomainPackError(f"name={name!r} 与目录名 {pack_dir.name!r} 不一致")

    label = raw.get("label")
    if not isinstance(label, str) or not label.strip():
        raise DomainPackError("缺 label")

    papers_raw = raw.get("papers")
    id_fields: list[str] = list(_LEGACY_ID_FIELDS)
    if papers_raw is not None:
        if not isinstance(papers_raw, dict):
            raise DomainPackError("papers 应为映射")
        if "id_fields" in papers_raw:
            id_fields = _as_str_list(papers_raw.get("id_fields"), "papers.id_fields")
            if not id_fields:
                raise DomainPackError("papers.id_fields 不得为空列表")

    eln_fields = _parse_eln(raw.get("eln"))
    if not eln_fields and name == DEFAULT_PACK_NAME:
        # 默认包没声明 eln.fields 时，回退到改造前的硬编码字段，
        # 保证「默认包行为与改造前完全一致」这条回归红线。
        eln_fields = [ElnField(key=k) for k in _LEGACY_ELN_FIELDS]

    return DomainPack(
        name=name,
        label=label.strip(),
        description=str(raw.get("description") or "").strip(),
        eln_fields=eln_fields,
        id_fields=id_fields,
        source_presets=_parse_source_presets(raw.get("source_presets")),
        tagging_questions=_parse_tagging(raw.get("tagging")),
        path=pack_dir,
        raw=raw,
    )


def _scan_packs() -> dict[str, DomainPack]:
    """扫描 domains/ 下全部包。坏包跳过（warning），不抛异常。"""
    packs: dict[str, DomainPack] = {}
    if not DOMAINS_DIR.is_dir():
        logger.warning("领域包目录不存在，全部领域功能降级: %s", DOMAINS_DIR)
        return packs

    for child in sorted(DOMAINS_DIR.iterdir()):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        try:
            pack = load_pack(child)
        except DomainPackError as exc:
            logger.warning("领域包加载失败，已跳过: %s (%s)", child.name, exc)
            continue
        except Exception as exc:  # 兜底：任何意外都不得炸启动
            logger.warning("领域包加载异常，已跳过: %s (%r)", child.name, exc)
            continue
        packs[pack.name] = pack

    return packs


@lru_cache(maxsize=1)
def _cached_packs() -> dict[str, DomainPack]:
    return _scan_packs()


def reload_packs() -> dict[str, DomainPack]:
    """清缓存后重扫（测试或热加载用）。"""
    _cached_packs.cache_clear()
    return _cached_packs()


def list_packs() -> list[DomainPack]:
    return list(_cached_packs().values())


def get_pack(name: str | None) -> DomainPack | None:
    """按名取包；未知名返回 None（调用方自行回退 default）。"""
    if not name:
        return None
    return _cached_packs().get(name)


def get_default_pack() -> DomainPack | None:
    return get_pack(DEFAULT_PACK_NAME)


def get_eln_fields(name: str | None = None) -> list[str]:
    """取指定包的 **frontmatter** ELN 字段名列表（顺序敏感）。

    语义边界（重要）：
    - 本函数服务于**后端导出 Markdown 的 frontmatter**，其顺序在 `default`
      包下必须与改造前 `_FRONTMATTER_FIELDS` 逐字段一致（date 在前、含
      attachments），这是回归红线。
    - **前端表单**的字段顺序/label 是另一套语义，见 `DomainPack.form_eln_fields`
      与 `GET /api/domains` 的 `eln.form_fields`。二者在 default 包刻意不同
      （改造前真实情况就是如此），故不可混用。

    找不到包时回退到 `default`；再找不到则回退到改造前的硬编码快照。
    """
    pack = get_pack(name) or get_default_pack()
    # default 包（含回退路径）必须返回快照顺序，不得用 pack.yaml 的表单顺序。
    if pack is None or pack.name == DEFAULT_PACK_NAME:
        return list(_LEGACY_ELN_FIELDS)
    if pack.eln_fields:
        return pack.eln_field_keys
    return list(_LEGACY_ELN_FIELDS)


def get_id_fields(name: str | None = None) -> list[str]:
    """取指定包的 papers 主键字段。回退策略同 get_eln_fields。"""
    pack = get_pack(name) or get_default_pack()
    if pack is not None and pack.id_fields:
        return list(pack.id_fields)
    return list(_LEGACY_ID_FIELDS)
