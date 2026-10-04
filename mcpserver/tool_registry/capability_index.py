"""capability_index.py — 工具能力索引（(动词, 宾语域) 二元组）+ 跨源冲突消歧。

卷189-A2 落地。设计目标：把"这堆工具能干什么"从**翻 manifest 目录**变成
**按 (动词, 宾语域) 二元组查询**——如 ("search","papers") / ("decode","rf_signal")
/ ("convert","chem_smiles")。

数据来源：manifest 顶层 `capability_pairs` 字段，形如：
    "capability_pairs": [["search", "papers"], ["fuse", "pollination"]]

为什么用 `capability_pairs` 而不是工单草拟的 `capabilities`：manifest 的
`capabilities` 字段已被占用（既可能是 {"invocationCommands":[...]} 的调用契约，
也可能是字符串能力名数组，见 convert_manifest_to_meta），同一 key 不能兼作
二元组列表——故另起字段名，零破坏兼容（卷189 报告已记录此取舍）。

跨源冲突消歧（与 mcp_registry._SOURCE_PRIORITY 的区别）：
- mcp_registry._SOURCE_PRIORITY = {mcporter:1, manifest:2, adapter:3} —— 语义是
  **登记覆盖优先级**（谁写入覆盖谁，adapter 最高）。
- 本模块 DEFAULT_SOURCE_PRIORITY = {manifest:3, adapter:2, mcporter:1} —— 语义是
  **默认选中优先级**（同为内置 > adapter > 外部，与工单一致）。两套语义不同，
  故意分开：登记是"数据落哪张表"，索引是"用户该调哪个"。

纯 Python 标准库，零新依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# 默认选中优先级（数字越大越优先）：内置 > adapter > 外部
# 与 mcp_registry 的登记覆盖优先级语义不同，见模块 docstring。
DEFAULT_SOURCE_PRIORITY: dict[str, int] = {
    "manifest": 3,   # 内置 agent（本仓 mcpserver/*/agent-manifest.json）
    "adapter": 2,    # 第三方 adapter 能力包
    "mcporter": 1,   # mcporter 外部配置服务
}


@dataclass(frozen=True)
class CapabilityEntry:
    """一条能力声明：某个服务提供 (verb, domain) 能力。"""

    name: str          # 服务名（registry key）
    verb: str          # 动词：search/convert/decode/fuse/compute/...
    domain: str        # 宾语域：papers/rf_signal/chem_smiles/...
    source: str        # manifest / adapter / mcporter
    priority: int = 0  # 默认选中优先级（越大越优先）

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "verb": self.verb,
            "domain": self.domain, "source": self.source,
            "priority": self.priority,
        }


@dataclass
class ResolvedCapability:
    """消歧结果：默认选中项 + 其余的别名（同能力但非首选）。"""

    verb: str
    domain: str
    default: CapabilityEntry | None
    aliases: list[CapabilityEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "verb": self.verb,
            "domain": self.domain,
            "default": self.default.as_dict() if self.default else None,
            "aliases": [a.as_dict() for a in self.aliases],
        }


def _normalize(text: str) -> str:
    """归一化动词/域：小写 + 去首尾空白（查询与声明两侧都跑，保证匹配）。"""
    return str(text or "").strip().lower()


def parse_capability_pairs(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """从 manifest 提取 (verb, domain) 二元组列表。

    只认顶层 `capability_pairs`；容忍三种写法（增量兼容，不因一条坏行整体失败）：
      [["search","papers"], ...] / [{"verb":"search","domain":"papers"}, ...] /
      "search:papers" 字符串。缺字段 / 空 → 返回 []。
    """
    if not isinstance(manifest, dict):
        return []
    raw = manifest.get("capability_pairs")
    if not raw:
        return []
    out: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        raw = list(raw.items())
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            verb, domain = _normalize(item[0]), _normalize(item[1])
        elif isinstance(item, dict):
            verb = _normalize(item.get("verb", ""))
            domain = _normalize(item.get("domain", ""))
        elif isinstance(item, str) and ":" in item:
            verb, _, domain = item.partition(":")
            verb, domain = _normalize(verb), _normalize(domain)
        else:
            continue  # 坏条目跳过，不影响其余
        if verb and domain:
            out.append((verb, domain))
    return out


class CapabilityIndex:
    """(动词, 宾语域) → 服务 的索引，含跨源冲突消歧。

    用法：
        idx = CapabilityIndex()
        idx.add("paper_miner", [("search","papers")], source="manifest")
        idx.add("rf_brain",    [("decode","rf_signal")], source="manifest")
        r = idx.resolve("search", "papers")   # → ResolvedCapability(default=...)
    """

    def __init__(self, source_priority: dict[str, int] | None = None):
        # {(verb, domain): [CapabilityEntry, ...]}
        self._buckets: dict[tuple[str, str], list[CapabilityEntry]] = {}
        # {verb: {domain}} / {domain: {verb}} 便于前缀式查询
        self._verbs: dict[str, set[str]] = {}
        self._domains: dict[str, set[str]] = {}
        self._priorities = dict(DEFAULT_SOURCE_PRIORITY)
        if source_priority:
            self._priorities.update(source_priority)

    # ---- 构建 ----

    def add(self, name: str, pairs: Iterable[tuple[str, str]],
            source: str = "manifest") -> int:
        """登记一个服务的能力对；返回成功登记条数。重复 (name,verb,domain) 自动去重。"""
        prio = self._priorities.get(source, 0)
        added = 0
        for verb, domain in pairs:
            verb, domain = _normalize(verb), _normalize(domain)
            if not verb or not domain:
                continue
            bucket = self._buckets.setdefault((verb, domain), [])
            if any(e.name == name for e in bucket):
                continue  # 同源同名同能力，幂等
            bucket.append(CapabilityEntry(name=name, verb=verb, domain=domain,
                                          source=source, priority=prio))
            self._verbs.setdefault(verb, set()).add(domain)
            self._domains.setdefault(domain, set()).add(verb)
            added += 1
        return added

    def add_manifest(self, name: str, manifest: dict[str, Any],
                     source: str = "manifest") -> int:
        """便捷：直接从 manifest 顶层 capability_pairs 提取并登记。"""
        return self.add(name, parse_capability_pairs(manifest), source=source)

    # ---- 查询 ----

    def resolve(self, verb: str, domain: str) -> ResolvedCapability:
        """按 (verb, domain) 消歧：priority 最高者为 default，其余为 alias。

        同 priority 时按 name 字典序稳定排序（可复现，便于测试断言）。
        """
        verb, domain = _normalize(verb), _normalize(domain)
        entries = list(self._buckets.get((verb, domain), []))
        entries.sort(key=lambda e: (-e.priority, e.name))
        return ResolvedCapability(
            verb=verb, domain=domain,
            default=entries[0] if entries else None,
            aliases=entries[1:],
        )

    def lookup(self, verb: str, domain: str | None = None) -> list[CapabilityEntry]:
        """模糊查询：domain 为 None 时返回该动词下全部条目（按优先级）。"""
        verb = _normalize(verb)
        if domain is None:
            out: list[CapabilityEntry] = []
            for (v, _d), entries in self._buckets.items():
                if v == verb:
                    out.extend(entries)
            out.sort(key=lambda e: (-e.priority, e.domain, e.name))
            return out
        return list(self._buckets.get((verb, _normalize(domain)), []))

    def by_verb(self, verb: str) -> list[str]:
        """该动词涉及的宾语域清单（sorted）。"""
        return sorted(self._domains_of(verb))

    def by_domain(self, domain: str) -> list[str]:
        """该宾语域涉及的动词清单（sorted）。"""
        return sorted(self._verbs_of(domain))

    def _domains_of(self, verb: str) -> set[str]:
        verb = _normalize(verb)
        return {d for (v, d) in self._buckets if v == verb}

    def _verbs_of(self, domain: str) -> set[str]:
        domain = _normalize(domain)
        return {v for (v, d) in self._buckets if d == domain}

    def services(self) -> list[str]:
        """索引中的服务名清单（去重 sorted）。"""
        return sorted({e.name for entries in self._buckets.values() for e in entries})

    # ---- 报告 ----

    def describe(self) -> dict[str, Any]:
        """汇总：二元组数 / 服务数 / 各动词域分布 / 冲突清单（供报告与端点）。"""
        conflicts = []
        for (verb, domain), entries in sorted(self._buckets.items()):
            if len(entries) > 1:
                r = self.resolve(verb, domain)
                conflicts.append({
                    "verb": verb, "domain": domain,
                    "default": r.default.name if r.default else None,
                    "aliases": sorted(a.name for a in r.aliases),
                })
        return {
            "pair_count": len(self._buckets),
            "service_count": len(self.services()),
            "verbs": sorted(self._verbs.keys()),
            "domains": sorted(self._domains.keys()),
            "conflicts": conflicts,
        }


def build_index(manifests: dict[str, dict[str, Any]],
                sources: dict[str, str] | None = None) -> CapabilityIndex:
    """从 {服务名: manifest} 批量建索引；sources 可指定各服务来源（默认 manifest）。"""
    sources = sources or {}
    idx = CapabilityIndex()
    for name, manifest in manifests.items():
        idx.add_manifest(name, manifest, source=sources.get(name, "manifest"))
    return idx
