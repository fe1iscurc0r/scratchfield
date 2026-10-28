#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cron_to_workorder.py —— 日报 → 工单草稿自动转化器（工单 240 · 漏斗 2.0 闭环）

把「cron 每天产出的日报」自动抽成「可入池的工单草稿」，落盘供人工审批。
没有它，漏斗 2.0 的末端（日报 → 工单）是断头路（设计稿 §0「漏斗中断」）。

模式
----
  --scan             扫描近 --period 的日报 → 草稿落盘 --output（默认 auto_<day>/）
  --list-sources     打印 cron 源清单 + 在本仓的解析结果 + 「工单假设路径」偏差
  --promote <draft>  草稿 → 仓库根 TRAE_WORKORDER_PROMPT_AGENT_<n>.md（默认 dry-run）

路径口径（重要）
--------------
本仓已连续六次出现「工单/设计稿写的路径不是本仓路径」（工单 210/228/229/237/239/240）。
本模块因此对每个 cron 源**同时**记录 `assumed`（工单原文路径）与 `patterns`（2026-10-14
实测路径），运行时以 patterns 为准，偏差在 `--list-sources` 里如实打印。

LLM 口径（不静默降级）
--------------------
`--model` 非空 **且** 环境变量 `M3_API_KEY`（或 `DIGEST_API_KEY`）存在时，走 litellm 按
工单 §6 模板归纳；否则降级为**规则模式**（原文片段摘录 + 模板拼接 PoC），并在
**stdout 与每份草稿头部**显式注明模式。规则模式零 API 消耗、可离线复现。

时间窗口口径
------------
日报文件名带日期，而 git 场景下 mtime 会漂移到 clone 日 → **文件名日期优先**。
`--period` 按**日期粒度**解释：`24h` ≡ 当日，`48h` ≡ 当日+前一日，`Nd` ≡ 近 N 日，`all` ≡ 不限。
无日期文件名的文件是否接受 mtime 兜底由 `--mtime-fallback` 控制（默认 auto，
可复现场景建议 off）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAFTS_DIR = REPO_ROOT / "research" / "workorder_drafts"
ROOT_WORKORDER_RE = re.compile(r"^TRAE_WORKORDER_PROMPT_AGENT_(\d+)\.md$")

MAX_DRAFT_BYTES = 2048
SLUG_MAX = 40
EXCERPT_MAX = 80
TITLE_MAX = 60

# ---------------------------------------------------------------- cron 源清单
# assumed  = 工单 §2 里写的路径（**多处与实况不符**，保留作对账凭据）
# patterns = 2026-10-14 在 main 全树（25,065 条目）实测存在的路径


@dataclass(frozen=True)
class CronSource:
    """一个 cron 产出源：工单假设路径 + 本仓实测路径。"""

    cron_id: str
    name: str
    assumed: tuple[str, ...]
    patterns: tuple[str, ...]
    theme: str

    def resolve(self, root: Path) -> list[Path]:
        """按 patterns 在本仓解析文件（存在才返回，去重 + 路径序）。"""
        out: set[Path] = set()
        for pat in self.patterns:
            out.update(p for p in root.glob(pat) if p.is_file())
        return sorted(out)


SOURCES: tuple[CronSource, ...] = (
    CronSource(
        "a37ffecbd730",
        "GitHub 扫货日报",
        ("docs/GitHub-Sweep-Daily-*.md",),
        ("docs/GitHub-Sweep-Daily-*.md",),
        "other",
    ),
    CronSource(
        "ad17cd9d341f",
        "论文流水线-每日增量扫+授粉",
        ("research/papers/digests/",),
        ("docs/paper-round*/digests/digest-*.md", "docs/paper-round*/digests/授粉点-统一.md"),
        "biomass",
    ),
    CronSource(
        "bda7241fa9c3",
        "授粉流水线-超限战轮",
        ("research/papers/pollination/",),
        ("docs/超限战轮*-授粉报告-*.md", "docs/pollination/batches/*.md"),
        "other",
    ),
    CronSource(
        "0081aeb248b2",
        "DeepSeek-Harness-每日 Trending",
        ("docs/DeepSeek-Harness-Trending-*.md",),
        ("docs/GitHub-Trending-*.md", "docs/扫货-GH*.md"),
        "agent",
    ),
    CronSource(
        "67c43c05f468",
        "RSS→规则自生成",
        ("decision_layer/rules/*.yaml",),
        ("decision_layer/rules/*.yaml",),
        "other",
    ),
)

SOURCE_BY_ID = {s.cron_id: s for s in SOURCES}
DEFAULT_CRONS: tuple[str, ...] = tuple(s.cron_id for s in SOURCES[:5])


def find_overlaps(root: Path) -> dict[str, list[str]]:
    """被多个 cron 源同时认领的文件 → [cron_id, ...]。

    源定义重叠是 bug 温床：同一文件被两条源扫两遍，跨源去重时会把候选**错误归属**
    到排序靠前的那条源（2026-10-14 实测踩过：`docs/pollination/batches/GitHub扫货日报-*`
    同时命中 a37 与 bda ⇒ bda 的候选全被吞）。故把它做成显式守卫。
    """
    owner: dict[str, list[str]] = {}
    for src in SOURCES:
        for p in src.resolve(root):
            owner.setdefault(rel_to(p, root), []).append(src.cron_id)
    return {path: ids for path, ids in owner.items() if len(ids) > 1}

# ---------------------------------------------------------------- 关键词表
# 主题线（工单 §6 条件 3：biomass / sdr / agent / esp32 / pcb / other）
THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "biomass": (
        "biomass", "生物质", "lignin", "木质素", "pyrolysis", "热解", "hydrogel", "水凝胶",
        "rheology", "流变", "spectroscop", "光谱", "cellulose", "纤维素",
    ),
    "sdr": (
        "sdr", "software defined radio", "射频", "radio", "spectrum", "频谱", "antenna", "天线",
        "lora", "rf ", "decoder", "解码",
    ),
    "agent": ("agent", "mcp", "llm", "rag", "记忆", "memory", "graphrag", "知识图谱"),
    "esp32": ("esp32", "固件", "firmware", "mcu", "microcontroller"),
    "pcb": ("pcb", "kicad", "schematic", "原理图", "拓扑", "topology"),
}

# 门槛 A：可执行 PoC 入口线索（工单 §6 条件 1）
POC_HINTS: tuple[str, ...] = (
    "mcp", "server", "api", "cli", "sdk", "library", "toolkit", "framework", "runtime",
    "engine", "pipeline", "adapter", "plugin", "算法", "工具", "框架", "引擎", "库",
)

# 门槛 B：代码/论文支撑线索（工单 §6 条件 2）
ARXIV_RE = re.compile(r"(arxiv\.org/abs/\d{4}\.\d{4,5}|arXiv:\s*\d{4}\.\d{4,5}|\b\d{4}\.\d{4,5}(?:v\d+)?\b)")
GITHUB_URL_RE = re.compile(r"github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)")
SLUG_CELL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")

# 路径前缀白名单外的 token 不得当仓库 slug（`docs/xxx` 这类不是 GitHub 仓库）
SLUG_OWNER_BLOCKLIST = frozenset({
    "docs", "research", "src", "mcpserver", "tools", "tests", "apiserver", "agentserver",
    "rag", "frontend", "skills", "vendor", "cron", "scripts", "reports", "workorders",
    "papers", "system", "archive", "domains", "mod", "coupled", "firmware", "vault",
    "references", "academic", "characters", "carpet", "guide_engine", "sitaware", "voice",
})

OK_LICENSES = ("mit", "apache", "bsd", "isc", "mpl")
RISKY_LICENSES = ("gpl", "agpl", "lgpl", "sspl", "none", "noassertion", "source-available", "bsl", "elastic")

SECTION_RE = re.compile(r"^#{2,3}\s*(.+?)\s*$")
FILE_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
PERIOD_RE = re.compile(r"^(\d+)([hd])$")


# ================================================================ 纯函数层
MD_NOISE_RE = re.compile(r"(\*\*|~~|`)")


def clip(text: str, limit: int) -> str:
    """去掉 markdown 强调噪声、压平空白后截断，超长加省略号。"""
    flat = " ".join(MD_NOISE_RE.sub("", text).split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def slugify(text: str, limit: int = SLUG_MAX) -> str:
    """英文/数字 slug；非字母数字压成 `-`。"""
    s = re.sub(r"[^0-9a-zA-Z]+", "-", text.strip().lower()).strip("-")
    return s[:limit].rstrip("-") or "untitled"


def parse_period(period: str) -> int | None:
    """`24h` / `7d` / `all` → 窗口秒数（`all` → None）。非法值抛 ValueError。"""
    p = period.strip().lower()
    if p == "all":
        return None
    m = PERIOD_RE.match(p)
    if not m:
        raise ValueError(f"无法解析 --period {period!r}（期望 24h / 7d / all）")
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        raise ValueError(f"--period 必须为正：{period!r}")
    return n * (3600 if unit == "h" else 86400)


def window_days(seconds: int | None) -> int | None:
    """窗口秒数 → 日期粒度天数（None = 不限）。"""
    if seconds is None:
        return None
    return max(1, -(-seconds // 86400))  # ceil


def file_ref_date(path: Path, mtime_fallback: bool = True) -> _dt.date | None:
    """文件参考日期：文件名里的日期优先（git 场景 mtime 会漂移到 clone 日）。"""
    m = FILE_DATE_RE.search(path.name)
    if m:
        try:
            return _dt.date.fromisoformat(m.group(1))
        except ValueError:
            pass
    if not mtime_fallback:
        return None
    try:
        return _dt.date.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def in_window(path: Path, today: _dt.date, days: int | None, mtime_fallback: bool = True) -> bool:
    """文件是否落在窗口内（日期粒度，含首尾）。"""
    if days is None:
        return True
    ref = file_ref_date(path, mtime_fallback=mtime_fallback)
    if ref is None:
        return False
    return 0 <= (today - ref).days < days


def match_themes(text: str) -> list[str]:
    """命中主题线（可多个，按 THEME_KEYWORDS 声明序）。"""
    low = f" {text.lower()} "
    return [theme for theme, kws in THEME_KEYWORDS.items() if any(k in low for k in kws)]


def match_poc_hints(text: str) -> list[str]:
    """门槛 A：命中的可执行 PoC 入口线索。"""
    low = text.lower()
    return [h for h in POC_HINTS if h in low]


def has_code_support(text: str) -> bool:
    """门槛 B：有 GitHub 仓库 slug / github.com 链接 / arXiv 编号。"""
    return bool(ARXIV_RE.search(text) or GITHUB_URL_RE.search(text) or extract_slug(text))


def extract_slug(text: str) -> str:
    """从一行里抽出仓库 slug（`owner/repo`）；抽不到返回空串。"""
    url = GITHUB_URL_RE.search(text)
    if url:
        return f"{url.group(1)}/{url.group(2)}"
    for cell in (c.strip() for c in text.strip().strip("|").split("|")):
        if SLUG_CELL_RE.match(cell):
            owner = cell.split("/", 1)[0].lower()
            if owner not in SLUG_OWNER_BLOCKLIST:
                return cell
    return ""


def extract_arxiv_pid(text: str) -> str:
    """从一行里抽出 arXiv 编号（论文 digest 表首列就是它）；抽不到返回空串。"""
    m = ARXIV_RE.search(text)
    if not m:
        return ""
    return re.sub(r"^(arxiv\.org/abs/|arXiv:\s*)", "", m.group(0)).strip()


def row_desc(cells: list[str]) -> str:
    """取该行的「描述」列：末列够长就用末列，否则退回最长列。"""
    if not cells:
        return ""
    last = cells[-1]
    return last if len(last) >= 8 else max(cells, key=len)


def rel_to(path: Path, root: Path) -> str:
    """相对 root 的 posix 路径；不在 root 下时退回绝对 posix（`--output` 可在仓外）。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


REF_LIKE_RE = re.compile(r"\.(md|json|py|ya?ml|csv|txt)$", re.IGNORECASE)


def looks_like_ref(cell: str) -> bool:
    """该单元格看起来是文件名/文档引用，而不是标题或描述。"""
    return bool(REF_LIKE_RE.search(cell.strip())) and len(cell.strip()) < 80


def assess_risk(line: str, section: str) -> tuple[str, str]:
    """规则风险评估：返回 (等级, 理由)。"""
    low = f"{line} {section}".lower()
    if any(w in low for w in ("archived", "排除", "无 licens", "noassertion")):
        return "高", "报告内标为排除/归档/LICENSE 缺失"
    if any(w in low for w in RISKY_LICENSES):
        return "高", "copyleft 或 source-available，与主仓许可口径冲突"
    if any(w in low for w in ("已评估", "已授粉", "已蒸馏", "已同步", "已引用")):
        return "中", "本地已有评估/授粉记录，重复入池风险"
    if any(w in low for w in ("ip 风险", "风险", "暂缓", "误报")):
        return "中", "报告内显式标注风险或暂缓"
    if "推荐" in section:
        return "低", "报告 Top 推荐段，且未见排除口径"
    return "中", "未标注排除口径，但也不在推荐段"


def detect_license(line: str) -> str:
    """从表格行里猜许可证文本（找不到返回空串）。"""
    for cell in (c.strip() for c in line.strip().strip("|").split("|")):
        low = cell.lower()
        if low in OK_LICENSES or low in RISKY_LICENSES:
            return cell
        if "-" in cell and any(low.startswith(x) for x in ("apache", "bsd", "gpl", "lgpl")):
            return cell
    return ""


# ================================================================ 抽取层
@dataclass
class Candidate:
    """一条可入池的候选。"""

    source: CronSource
    report_rel: str
    title: str
    excerpt: str
    poc: str
    theme: str
    themes: tuple[str, ...]
    risk: str
    risk_reason: str
    slug: str
    license: str
    score: int
    mode: str


def _iter_table_rows(text: str):
    """产出 (section, line)：markdown 表格行 + 其所属二级/三级标题。"""
    section = ""
    for raw in text.splitlines():
        m = SECTION_RE.match(raw.strip())
        if m:
            section = m.group(1).strip()
            continue
        if raw.strip().startswith("|"):
            yield section, raw.strip()


def _row_skip(line: str, section: str) -> bool:
    """表头/分隔行/删除线行/排除段 —— 一律跳过。"""
    if set(line) <= set("|-: "):
        return True
    if "~~" in line:
        return True
    if "排除" in section or "状态确认" in section:
        return True
    return "项目 | 排除原因" in line


def extract_candidates(
    text: str,
    source: CronSource,
    report_rel: str,
    mode: str = "rule-based",
    max_items: int = 3,
) -> list[Candidate]:
    """规则抽取：双门槛筛（PoC 入口 + 代码/论文支撑）→ 打分取前 max_items。

    两类行都吃：
      * 扫货/Trending 表 —— 有 `owner/repo` slug 列 → 门槛 B 由 slug 满足；
      * 论文 digest 表 —— 首列是 arXiv 编号、无 slug → 门槛 B 由 arXiv 编号满足。
    """
    pool: list[Candidate] = []
    for section, line in _iter_table_rows(text):
        if _row_skip(line, section):
            continue
        slug = extract_slug(line)
        arxiv = "" if slug else extract_arxiv_pid(line)
        if not slug and not arxiv:
            continue
        ident = slug or f"arXiv:{arxiv}"
        cells = [c.strip() for c in line.strip("|").split("|")]
        desc = row_desc(cells)
        if not desc:
            continue
        blob = f"{line} {section}"
        support = "arxiv" if arxiv else "repo"
        poc_hits = match_poc_hints(desc)
        if not poc_hits:
            continue  # 门槛 A 不满足 → 丢弃
        themes = match_themes(blob)
        theme = themes[0] if themes else source.theme
        risk, reason = assess_risk(line, section)
        lic = detect_license(line)
        score = 3 * len(themes) + len(poc_hits)
        score += 2 if "推荐" in section else 0
        score += 1 if lic.lower() in OK_LICENSES else 0
        score += 1 if support == "arxiv" else 0
        score -= {"低": 0, "中": 1, "高": 4}[risk]
        caption = desc
        if not caption or caption == ident or looks_like_ref(caption):
            alt = next(
                (c for c in cells if len(c) >= 8 and c != ident and not looks_like_ref(c)),
                "",
            )
            caption = alt or ident
        title = clip(f"{ident} —— {caption}", TITLE_MAX)
        pool.append(
            Candidate(
                source=source,
                report_rel=report_rel,
                title=title,
                excerpt=clip(desc, EXCERPT_MAX),
                poc=_rule_poc(ident, lic, theme, poc_hits, mode),
                theme=theme,
                themes=tuple(themes),
                risk=risk,
                risk_reason=reason,
                slug=ident,
                license=lic,
                score=score,
                mode=mode,
            )
        )
    pool.sort(key=lambda c: (-c.score, c.slug))
    return pool[: max(0, max_items)]


def _rule_poc(slug: str, lic: str, theme: str, poc_hits: list[str], mode: str) -> str:
    """规则模式下的「候选 PoC」—— 模板拼接，显式标注来源。"""
    entry = " / ".join(poc_hits[:3])
    lic_txt = f"（{lic}）" if lic else ""
    tail = "摘录系原文片段，未做 LLM 归纳" if mode.startswith("rule") else "LLM 归纳"
    return f"把 `{slug}`{lic_txt} 的 `{entry}` 能力接入 `{theme}` 线（[规则生成] {tail}）"


# ================================================================ LLM 层
PROMPT_TEMPLATE = """你是一个日报工单提取器。

输入：一段日报 markdown（含 GitHub 扫货 / 论文 digest / 授粉点 / Trending）
任务：识别其中"可入池工单"的条目（同时满足以下条件）：
  1. 有具体 PoC 入口（API/工具/库/算法）
  2. 有论文或代码支撑（GitHub 链接 / arxiv 链接 / 具体 commit）
  3. 与 scratchpad 主题线相关（biomass / sdr / agent / esp32 / pcb / other）

输出：1-3 条候选，每条包含：
  - 候选标题（一句话）
  - 来源报告（哪份日报）
  - 摘录（原文 ≤ 80 字）
  - 候选 PoC（一句话）
  - 风险评估（低/中/高）

不输出未达双门槛的内容。只输出 JSON 数组，元素形如
{"title": "...", "excerpt": "...", "poc": "...", "risk": "低"}
"""


def llm_extract(text: str, source: CronSource, model: str, report_rel: str, max_items: int):
    """litellm 归纳。返回 (candidates, mode_str)；不可用时返回 (None, 原因)。"""
    key = os.environ.get("M3_API_KEY") or os.environ.get("DIGEST_API_KEY")
    if not model:
        return None, "no-model"
    if not key:
        return None, "no-key"
    try:
        import litellm  # noqa: PLC0415  延迟导入：无 key 时不该付 import 代价
    except ImportError:
        return None, "no-litellm"
    kwargs: dict[str, object] = {"model": model, "api_key": key, "messages": [
        {"role": "system", "content": PROMPT_TEMPLATE},
        {"role": "user", "content": text[:12000]},
    ]}
    base = os.environ.get("M3_API_BASE")
    if base:
        kwargs["api_base"] = base
    try:
        resp = litellm.completion(timeout=60, **kwargs)
        body = resp["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001  任何 LLM 侧故障都降级，不阻断扫报
        return None, f"llm-error:{type(exc).__name__}"
    items = _parse_llm_json(body)
    if items is None:
        return None, "llm-unparsable"
    out: list[Candidate] = []
    for it in items[:max_items]:
        title = clip(str(it.get("title", "")), TITLE_MAX) or source.name
        out.append(
            Candidate(
                source=source,
                report_rel=report_rel,
                title=title,
                excerpt=clip(str(it.get("excerpt", "")), EXCERPT_MAX),
                poc=clip(str(it.get("poc", "")), EXCERPT_MAX),
                theme=source.theme,
                themes=match_themes(f"{title} {it.get('excerpt', '')}"),
                risk=str(it.get("risk", "中")),
                risk_reason="LLM 归纳",
                slug=extract_slug(str(it.get("title", ""))),
                license="",
                score=100 - len(out),
                mode=f"llm({model})",
            )
        )
    return (out or None), f"llm({model})"


def _parse_llm_json(body: str):
    """从 LLM 回复里抠出 JSON 数组；抠不出返回 None。"""
    m = re.search(r"\[[\s\S]*\]", body)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


# ================================================================ 渲染层
def render_draft(cand: Candidate, cand_number: str, day: str) -> str:
    """渲染单份草稿 —— 与 TRAE_WORKORDER_PROMPT_AGENT_*.md 同构（首行 `# 工单 <n> · <标题>`）。"""
    theme_txt = ", ".join(f"`{t}`" for t in cand.themes) if cand.themes else f"`{cand.theme}`"
    return f"""# 工单 {cand_number} · {cand.title}

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：`cron_to_workorder`（自动）· 日期：{day}
> **来源 cron**：`{cand.source.cron_id}` {cand.source.name} · **来源报告**：`{cand.report_rel}`
> **生成模式**：{cand.mode}
> ⚠️ 本文件是**自动草稿**，未经人工审阅；`--promote` 前须师傅签字（设计稿 §5「必须人工 --promote」）

## §0 · 摘录（原文 ≤ {EXCERPT_MAX} 字）

> {cand.excerpt}

## §1 · 候选 PoC

{cand.poc}

## §2 · 主题线归属

{theme_txt}

## §3 · 风险评估

**{cand.risk}** —— {cand.risk_reason}

## §4 · 待补（人工填）

- [ ] PoC 边界与验收标准
- [ ] 与现有模块的耦合点（`mcpserver/` / `agentserver/` / `apiserver/` / `coupled/`）
- [ ] 是否与已发工单重复（查 main 根 `TRAE_WORKORDER_PROMPT_AGENT_*.md`）
"""


def enforce_size(text: str, limit: int = MAX_DRAFT_BYTES) -> str:
    """把草稿压到 limit 字节内（按字节截断且不切断 UTF-8 字符）。"""
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    marker = "\n\n> ⚠️ 草稿超长已截断（上限 %d B）\n" % limit
    budget = limit - len(marker.encode("utf-8"))
    cut = raw[:budget].decode("utf-8", errors="ignore")
    return cut + marker


def next_root_number(root: Path) -> int:
    """仓库根现有 TRAE 工单最大编号 + 1。"""
    nums = [
        int(m.group(1))
        for p in root.iterdir()
        if p.is_file() and (m := ROOT_WORKORDER_RE.match(p.name))
    ]
    return (max(nums) + 1) if nums else 1


# ================================================================ 驱动层
def dedupe_candidates(cands: list[Candidate]) -> tuple[list[Candidate], int]:
    """跨日报去重：同一标识（slug / arXiv id，大小写不敏感）只留最高分那条。"""
    best: dict[str, Candidate] = {}
    for c in cands:
        key = c.slug.lower()
        if key not in best or c.score > best[key].score:
            best[key] = c
    uniq = sorted(best.values(), key=lambda c: (-c.score, c.slug))
    return uniq, len(cands) - len(uniq)


def pick_round_robin(uniq: list[Candidate], cron_ids: list[str], max_total: int) -> list[Candidate]:
    """按 cron 轮转取前 max_total 条 —— 保证首批草稿**覆盖面**优先于单源密度。

    各源内部保持分数降序；某个源取空就跳过，直到凑够 max_total 或全部取空。
    """
    by_src: dict[str, list[Candidate]] = {cid: [] for cid in cron_ids}
    for c in uniq:
        by_src.setdefault(c.source.cron_id, []).append(c)
    picked: list[Candidate] = []
    while len(picked) < max_total:
        progressed = False
        for cid in cron_ids:
            if len(picked) >= max_total:
                break
            pool = by_src.get(cid) or []
            if pool:
                picked.append(pool.pop(0))
                progressed = True
        if not progressed:
            break
    return picked


def _scan_source(
    source: CronSource,
    root: Path,
    today: _dt.date,
    days: int | None,
    mtime_fallback: bool,
    model: str,
    max_per_file: int,
):
    """扫一个 cron 源 → (candidates, files 计数, 模式计数)。"""
    files = [p for p in source.resolve(root) if in_window(p, today, days, mtime_fallback)]
    cands: list[Candidate] = []
    modes: dict[str, int] = {}
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = rel_to(f, root)
        got, mode = llm_extract(text, source, model, rel, max_per_file)
        if got is None:
            mode = "rule-based" if mode in {"no-model", "no-key", "no-litellm"} else f"rule-based(降级自 {mode})"
            got = extract_candidates(text, source, rel, mode="rule-based", max_items=max_per_file)
        modes[mode] = modes.get(mode, 0) + 1
        cands.extend(got)
    return cands, files, modes


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    today = _dt.date.fromisoformat(args.date) if args.date else _dt.date.today()
    days = window_days(parse_period(args.period))
    mfb = args.mtime_fallback == "auto"
    cron_ids = list(args.crons) if args.crons else list(DEFAULT_CRONS)
    unknown = [c for c in cron_ids if c not in SOURCE_BY_ID]
    if unknown:
        print(f"[scan] 未知 cron id: {unknown}（可用: {sorted(SOURCE_BY_ID)}）", file=sys.stderr)
        return 2

    out_dir = Path(args.output) if args.output else DRAFTS_DIR / f"auto_{today.isoformat()}"
    base = args.cand_base if args.cand_base is not None else next_root_number(root)

    print(f"[scan] repo={root} today={today.isoformat()} period={args.period} days={days} "
          f"mtime_fallback={'on' if mfb else 'off'} model={args.model or '(空→规则模式)'}")

    all_cands: list[Candidate] = []
    source_lines: list[str] = []
    for cid in cron_ids:
        src = SOURCE_BY_ID[cid]
        cands, files, modes = _scan_source(
            src, root, today, days, mfb, args.model, args.max_per_file
        )
        mode_txt = ", ".join(f"{k}×{v}" for k, v in sorted(modes.items())) or "无文件"
        source_lines.append(
            f"  {cid} {src.name}: 文件 {len(files)} / 候选 {len(cands)} / 模式 {mode_txt}"
        )
        all_cands.extend(cands)

    print("[scan] 源解析结果:")
    for line in source_lines:
        print(line)
    overlaps = find_overlaps(root)
    if overlaps:
        print(f"[scan] ⚠️ 源定义重叠 {len(overlaps)} 处 —— 候选归属可能被排序掩盖，请先修 SOURCES")
        for path, ids in sorted(overlaps.items())[:5]:
            print(f"[scan]     {path} ← {ids}")

    all_cands.sort(key=lambda c: (-c.score, c.source.cron_id, c.slug))
    uniq, dropped = dedupe_candidates(all_cands)
    picked = pick_round_robin(uniq, cron_ids, max(0, args.max_total))
    print(f"[scan] 候选合计 {len(all_cands)} / 去重后 {len(uniq)}（丢 {dropped} 条跨报重复）/ 取 {len(picked)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for i, cand in enumerate(picked):
        num = f"{base + i}"
        name = f"WO-{num}-{slugify(cand.title)}.md"
        body = enforce_size(render_draft(cand, num, today.isoformat()))
        dst = out_dir / name
        dst.write_text(body, encoding="utf-8", newline="\n")
        size = len(body.encode("utf-8"))
        assert size <= MAX_DRAFT_BYTES, f"{name} 超限 {size} B"
        assert dst.read_bytes().count(b"\r\n") == 0, f"{name} 行尾非 LF"
        written.append(
            {
                "file": rel_to(dst, root),
                "cron": cand.source.cron_id,
                "slug": cand.slug,
                "theme": cand.theme,
                "risk": cand.risk,
                "score": cand.score,
                "bytes": size,
                "mode": cand.mode,
                "source_report": cand.report_rel,
            }
        )
        print(f"[scan] + {rel_to(dst, root)}  ({size} B, {cand.mode}, risk={cand.risk})")

    manifest = out_dir / "_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "day": today.isoformat(),
                "period": args.period,
                "mtime_fallback": args.mtime_fallback,
                "model": args.model or "",
                "cand_base": base,
                "crons": cron_ids,
                "candidates_total": len(all_cands),
                "candidates_deduped": len(uniq),
                "duplicates_dropped": dropped,
                "source_overlaps": sorted(overlaps),
                "source_resolution": source_lines,
                "drafts": written,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
        newline="\n",
    )
    assert manifest.read_bytes().count(b"\r\n") == 0
    print(f"[scan] 落盘 {len(written)} 份草稿 → {out_dir}")
    print(f"[scan] manifest → {rel_to(manifest, root)}")
    return 0


def cmd_list_sources(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    print(f"[list-sources] repo={root}")
    print(f"{'cron id':<14} {'本仓命中':>8}  {'名称':<28} 工单假设路径（对账用）")
    for src in SOURCES:
        found = src.resolve(root)
        assumed = ", ".join(src.assumed)
        flag = "" if found else "  ← ⚠️ 本仓 0 命中"
        print(f"{src.cron_id:<14} {len(found):>8}  {src.name:<28} {assumed}{flag}")
    print("\n[list-sources] 实测样本（每个源最多 3 条）:")
    for src in SOURCES:
        found = src.resolve(root)
        if not found:
            continue
        print(f"  {src.cron_id} {src.name}:")
        for p in found[:3]:
            print(f"      {rel_to(p, root)}")
    overlaps = find_overlaps(root)
    if overlaps:
        print(f"\n[list-sources] ⚠️ 源重叠 {len(overlaps)} 处（同一文件被多条源认领）:")
        for path, ids in sorted(overlaps.items()):
            print(f"      {path}  ← {ids}")
    else:
        print("\n[list-sources] ✅ 无源重叠")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    root = Path(args.repo).resolve()
    src = Path(args.promote)
    if not src.is_absolute():
        src = (root / src).resolve() if (root / src).exists() else Path(args.promote).resolve()
    if not src.is_file():
        print(f"[promote] 找不到草稿 {src}", file=sys.stderr)
        return 2
    raw = src.read_text(encoding="utf-8")
    first = raw.splitlines()[0] if raw.splitlines() else ""
    if not first.startswith("# 工单 "):
        print(f"[promote] {src.name} 首行不是 `# 工单 <n> · …`，拒绝提升", file=sys.stderr)
        return 2
    num = args.next_number if args.next_number > 0 else next_root_number(root)
    dst = root / f"TRAE_WORKORDER_PROMPT_AGENT_{num}.md"
    if dst.exists():
        print(f"[promote] 目标已存在，拒绝覆写（幂等保护）：{dst.name}", file=sys.stderr)
        return 3
    title = first.split("·", 1)[1].strip() if "·" in first else ""
    new_first = f"# 工单 {num} · {title}"
    new_body = "\n".join([new_first, *raw.splitlines()[1:]])
    if not new_body.endswith("\n"):
        new_body += "\n"
    label = "APPLY" if args.apply else "DRY-RUN"
    print(f"[promote:{label}] {rel_to(src, root)}")
    print(f"[promote:{label}]   → {dst.name}")
    print(f"[promote:{label}]   首行: {first!r} → {new_first!r}")
    if not args.apply:
        print("[promote:DRY-RUN] 未落盘；加 --apply 生效")
        return 0
    dst.write_text(new_body, encoding="utf-8", newline="\n")
    assert dst.read_bytes().count(b"\r\n") == 0, "promote 落盘行尾非 LF"
    print(f"[promote:APPLY] 已写入 {dst.name}（git status 应显示 ??）")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="cron_to_workorder.py",
        description="日报 → 工单草稿自动转化器（工单 240）",
    )
    ap.add_argument("--repo", default=str(REPO_ROOT), help="仓库根（默认本文件所在仓库）")
    ap.add_argument("--scan", action="store_true", help="扫描日报并落盘草稿")
    ap.add_argument("--list-sources", action="store_true", help="打印 cron 源清单与解析结果")
    ap.add_argument("--promote", default="", help="把草稿提升为仓库根 TRAE_WORKORDER_PROMPT_AGENT_<n>.md")
    ap.add_argument("--period", default="24h", help="窗口：24h / 48h / 7d / all（默认 24h）")
    ap.add_argument("--date", default=None, help="覆盖'今天'（ISO 日期，测试/补跑用）")
    ap.add_argument("--output", default=None, help="草稿输出目录（默认 <repo>/research/workorder_drafts/auto_<day>/）")
    ap.add_argument("--crons", nargs="*", default=None, help="指定 cron id 列表（默认前 5 个）")
    ap.add_argument("--model", default=os.environ.get("M3_MODEL", ""), help="litellm 模型名；空则规则模式")
    ap.add_argument("--max-per-file", type=int, default=3, help="每个日报最多抽几条（默认 3）")
    ap.add_argument("--max-total", type=int, default=5, help="本次最多落盘几份草稿（默认 5）")
    ap.add_argument("--cand-base", type=int, default=None, help="草稿编号起点（默认根目录最大号 + 1）")
    ap.add_argument("--mtime-fallback", choices=("auto", "off"), default="auto",
                    help="无日期文件名是否用 mtime 兜底（可复现场景用 off）")
    ap.add_argument("--next-number", type=int, default=-1, help="--promote 的目标工单号（默认自动取下一个）")
    ap.add_argument("--apply", action="store_true", help="--promote 真正落盘（默认 dry-run）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.promote:
        return cmd_promote(args)
    if args.list_sources:
        return cmd_list_sources(args)
    if args.scan:
        return cmd_scan(args)
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
