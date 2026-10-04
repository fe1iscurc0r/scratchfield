"""压缩块 XML 模板 — consolidation 蒸馏输出标准化（03-03，claude-mem 授粉）。

借鉴点：claude-mem 的压缩块模板——LLM 蒸馏输出不再是无结构自由文本，而是
带占位符的 XML 结构块，可解析、可校验、可降级：

    <memory>
      <title>..</title>
      <fact>..</fact>
      <narrative>..</narrative>
      <concept>..</concept>
      <checkpoint>investigated|learned|completed|next_steps|notes</checkpoint>
    </memory>

三层容错（LLM 输出不完美是常态）：
1. ElementTree 解析（截取 <memory>..</memory> 后喂给解析器，允许块外噪声）；
2. ET 失败 → 正则逐字段抽取（容忍块内个别字段写坏 XML，如未转义 &）；
3. 完全无结构 → parsed=False 降级为整段文本（raw 原样返回，不丢内容）。

模板可配置（ModeConfig 风格，角色卡可切换）：MemoryTemplateConfig 数据类 +
TEMPLATE_MODES 预设，按模式取用字段子集与 checkpoint 词表。
纯标准库 xml.etree / re，不依赖 Claude SDK/Anthropic。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable
from xml.etree import ElementTree
from xml.sax.saxutils import escape

# checkpoint 词表（工单钦定五值）
CHECKPOINTS: tuple[str, ...] = (
    "investigated", "learned", "completed", "next_steps", "notes")
DEFAULT_CHECKPOINT = "notes"

_WRAPPER = "memory"
_FIELDS: tuple[str, ...] = ("title", "fact", "narrative", "concept",
                            "checkpoint")


@dataclass
class MemoryTemplateConfig:
    """压缩块模板配置（ModeConfig 风格）：字段子集 + checkpoint 词表可换。"""

    wrapper: str = _WRAPPER
    fields: tuple[str, ...] = _FIELDS
    checkpoints: tuple[str, ...] = CHECKPOINTS
    default_checkpoint: str = DEFAULT_CHECKPOINT

    def validate_checkpoint(self, value: str) -> str:
        """checkpoint 合法性：非法/空 → 默认值兜底（解析容错语义）。"""
        v = str(value or "").strip().lower()
        return v if v in self.checkpoints else self.default_checkpoint


# 角色卡预设（可切换）：default 全字段；compact 只留 title/fact/checkpoint
TEMPLATE_MODES: dict[str, MemoryTemplateConfig] = {
    "default": MemoryTemplateConfig(),
    "compact": MemoryTemplateConfig(
        fields=("title", "fact", "checkpoint")),
}


def get_template(mode: str = "default") -> MemoryTemplateConfig:
    """按模式取模板配置（未知模式 fail-fast 回 default 语义并注明）。"""
    cfg = TEMPLATE_MODES.get(str(mode or "").strip().lower())
    if cfg is None:
        raise ValueError(
            f"未知模板模式: {mode!r}（可用: {', '.join(TEMPLATE_MODES)}）")
    return cfg


# ---------------------------------------------------------------- 渲染

def render_memory_block(title: str = "", fact: str = "",
                        narrative: str = "", concept: str = "",
                        checkpoint: str = DEFAULT_CHECKPOINT,
                        config: MemoryTemplateConfig | None = None) -> str:
    """字段 → XML 压缩块。非法 checkpoint 直接抛错（渲染侧从严，写入前拦截）。"""
    cfg = config or get_template("default")
    cp = str(checkpoint or "").strip().lower()
    if cp not in cfg.checkpoints:
        raise ValueError(
            f"非法 checkpoint: {checkpoint!r}（合法值: "
            f"{', '.join(cfg.checkpoints)}）")
    values = {"title": title, "fact": fact, "narrative": narrative,
              "concept": concept, "checkpoint": cp}
    lines = [f"<{cfg.wrapper}>"]
    for name in cfg.fields:
        v = str(values.get(name) or "").strip()
        lines.append(f"  <{name}>{escape(v)}</{name}>")
    lines.append(f"</{cfg.wrapper}>")
    return "\n".join(lines)


# ---------------------------------------------------------------- 解析（容错）

_BLOCK_RE = re.compile(
    r"<(?P<w>\w+)[^>]*>(?P<body>.*?)</(?P=w)\s*>", re.DOTALL)
_FIELD_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _field_re(name: str) -> re.Pattern[str]:
    pat = _FIELD_RE_CACHE.get(name)
    if pat is None:
        pat = re.compile(
            rf"<{name}\s*>(?P<v>.*?)</{name}\s*>", re.DOTALL)
        _FIELD_RE_CACHE[name] = pat
    return pat


def _extract_fields(text: str) -> dict[str, str] | None:
    """正则逐字段抽取（ET 失败时的第二层容错）；一个字段都没有 → None。"""
    out: dict[str, str] = {}
    for name in _FIELDS:
        m = _field_re(name).search(text)
        if m:
            out[name] = m.group("v").strip()
    return out or None


def parse_memory_block(text: str,
                       config: MemoryTemplateConfig | None = None) -> dict[str, Any]:
    """LLM 蒸馏文本 → 结构化字段（三层容错，永不抛错）。

    返回：
    - parsed=True：title/fact/narrative/concept（缺失为 ""）+ checkpoint
      （非法/缺失兜底 default_checkpoint）；
    - parsed=False：raw=原文（解析失败降级为整段文本，不丢内容）。
    """
    cfg = config or get_template("default")
    src = str(text or "")
    # 第一层：截取 <memory>..</memory> 后 ET 解析（允许块外噪声）
    for m in _BLOCK_RE.finditer(src):
        body = m.group("body")
        try:
            root = ElementTree.fromstring(
                f"<{m.group('w')}>{body}</{m.group('w')}>")
        except ElementTree.ParseError:
            break  # ET 层失败 → 交正则层在同一片段上兜
        vals = {child.tag: (child.text or "").strip() for child in root}
        return {"parsed": True, "title": vals.get("title", ""),
                "fact": vals.get("fact", ""),
                "narrative": vals.get("narrative", ""),
                "concept": vals.get("concept", ""),
                "checkpoint": cfg.validate_checkpoint(
                    vals.get("checkpoint", ""))}
    # 第二层：正则逐字段抽取（容忍块内字段写坏 XML）
    fields = _extract_fields(src)
    if fields:
        return {"parsed": True, "title": fields.get("title", ""),
                "fact": fields.get("fact", ""),
                "narrative": fields.get("narrative", ""),
                "concept": fields.get("concept", ""),
                "checkpoint": cfg.validate_checkpoint(
                    fields.get("checkpoint", ""))}
    # 第三层：整段降级
    return {"parsed": False, "raw": src}


# ---------------------------------------------------------------- 合并

def _dedup_keep_order(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for it in items:
        s = str(it or "").strip()
        if s and s not in seen:
            seen.append(s)
    return seen


def _block_plain_lines(block: dict[str, Any]) -> list[str]:
    """已解析块 → 纯文本行（降级合并时保证输出统一为纯文本，无 XML 标记）。"""
    lines = []
    for name in _FIELDS:
        v = str(block.get(name) or "").strip()
        if v:
            lines.append(f"{name}: {v}")
    return lines


def merge_contents(contents: Iterable[str],
                   config: MemoryTemplateConfig | None = None) -> dict[str, Any]:
    """蒸馏合并多条内容：全为可解析块 → 渲染合并块；任一降级 → 纯文本拼接。

    返回 {content, used_xml}。这是 maintenance.consolidate 的合并内核：
    XML 路产出比自由文本更可解析的结构块；降级路把可解析块摊平为字段行后
    与自由文本统一拼接（输出纯文本，不产出半结构 XML 混排，内容不丢）。
    """
    cfg = config or get_template("default")
    srcs = [str(c or "") for c in contents]
    blocks = [parse_memory_block(c, cfg) for c in srcs]
    if not blocks or not all(b["parsed"] for b in blocks):
        lines: list[str] = []
        for b, c in zip(blocks, srcs):
            lines.extend(_block_plain_lines(b) if b["parsed"]
                         else [c.strip()] if c.strip() else [])
        return {"content": "\n".join(lines), "used_xml": False}
    titles = _dedup_keep_order(b["title"] for b in blocks)
    facts = _dedup_keep_order(b["fact"] for b in blocks)
    narratives = _dedup_keep_order(b["narrative"] for b in blocks)
    concepts = _dedup_keep_order(b["concept"] for b in blocks)
    cps = {b["checkpoint"] for b in blocks}
    merged_cp = cps.pop() if len(cps) == 1 else cfg.default_checkpoint
    content = render_memory_block(
        title="\n".join(titles), fact="\n".join(facts),
        narrative="\n".join(narratives), concept="\n".join(concepts),
        checkpoint=merged_cp, config=cfg)
    return {"content": content, "used_xml": True}


__all__ = [
    "CHECKPOINTS",
    "MemoryTemplateConfig",
    "TEMPLATE_MODES",
    "get_template",
    "merge_contents",
    "parse_memory_block",
    "render_memory_block",
]
