# -*- coding: utf-8 -*-
"""
instincts 行为规则库（W64-05）。
将项目级 / 全局级行为规范存为 YAML 规则，支持冲突时项目级覆盖；
提供 import/export/status（按领域分组+置信度条）；
trigger 字段对自然语言场景描述打分，返回匹配规则列表。

依赖：PyYAML（标准库 yaml）、numpy。
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """规则动作：描述名称 + 建议。"""
    name: str           # 动作类型，如 "warn", "block", "suggest"
    message: str         # 人类可读建议


@dataclass
class Evidence:
    """证据：引用来源。"""
    quote: str | None = None   # 直接引用
    url: str | None = None     # 参考链接


@dataclass
class InstinctRule:
    """单条行为规则。"""
    id: str                # 全局唯一 ID
    trigger: str            # 自然语言触发描述（用于匹配打分）
    confidence: float      # 置信度 [0, 1]
    domain: str             # 领域标签，如 "safety", "performance"
    source: str             # 来源描述，如 "ECC-2026"
    source_repo: str | None = None  # 来源仓库
    action: Action | None = None
    evidence: Evidence | None = None
    tags: list[str] = field(default_factory=list)   # 扩展标签

    @classmethod
    def from_dict(cls, d: dict) -> "InstinctRule":
        action = Action(**d["action"]) if "action" in d else None
        evidence = Evidence(**d["evidence"]) if "evidence" in d else None
        return cls(
            id=d["id"],
            trigger=d["trigger"],
            confidence=float(d["confidence"]),
            domain=d["domain"],
            source=d["source"],
            source_repo=d.get("source_repo"),
            action=action,
            evidence=evidence,
            tags=d.get("tags", []),
        )

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "trigger": self.trigger,
            "confidence": self.confidence,
            "domain": self.domain,
            "source": self.source,
        }
        if self.source_repo:
            out["source_repo"] = self.source_repo
        if self.action:
            out["action"] = {"name": self.action.name, "message": self.action.message}
        if self.evidence:
            out["evidence"] = {}
            if self.evidence.quote:
                out["evidence"]["quote"] = self.evidence.quote
            if self.evidence.url:
                out["evidence"]["url"] = self.evidence.url
        if self.tags:
            out["tags"] = self.tags
        return out


# ---------------------------------------------------------------------------
# 存储层：项目级 + 全局级
# ---------------------------------------------------------------------------

class InstinctStore:
    """两层规则存储：全局级 + 项目级（项目级同名规则覆盖全局级）。"""

    def __init__(self):
        self._global: dict[str, InstinctRule] = {}   # id → rule
        self._project: dict[str, dict[str, InstinctRule]] = defaultdict(dict)
        # ^ project_id → (id → rule)

    # ------------------------------------------------------------------
    # 添加规则
    # ------------------------------------------------------------------

    def add_global(self, rule: InstinctRule) -> None:
        """添加一条全局级规则。"""
        self._global[rule.id] = rule

    def add_project(self, project_id: str, rule: InstinctRule) -> None:
        """添加一条项目级规则（项目同名规则覆盖全局）。"""
        self._project[project_id][rule.id] = rule

    def add_rules_from_dicts(
        self, rules: list[dict], project_id: str | None = None
    ) -> int:
        """批量从 dict（反序列化 YAML）加载规则，返回加载数量。"""
        count = 0
        for d in rules:
            rule = InstinctRule.from_dict(d)
            if project_id:
                self.add_project(project_id, rule)
            else:
                self.add_global(rule)
            count += 1
        return count

    # ------------------------------------------------------------------
    # 查询（冲突时项目级覆盖全局级）
    # ------------------------------------------------------------------

    def get(self, rule_id: str, project_id: str | None = None) -> InstinctRule | None:
        """获取单条规则：优先项目级，其次全局级。"""
        if project_id and rule_id in self._project[project_id]:
            return self._project[project_id][rule_id]
        return self._global.get(rule_id) or None

    def get_effective(self, project_id: str) -> dict[str, InstinctRule]:
        """获取某项目的全部有效规则（项目级覆盖全局级）。"""
        effective = dict(self._global)
        effective.update(self._project[project_id])
        return effective

    def list_by_domain(
        self, project_id: str | None = None
    ) -> dict[str, list[InstinctRule]]:
        """按领域分组列出有效规则。"""
        rules = self.get_effective(project_id) if project_id else dict(self._global)
        by_domain: dict[str, list[InstinctRule]] = defaultdict(list)
        for rule in rules.values():
            by_domain[rule.domain].append(rule)
        # 每组内按置信度降序
        for domain in by_domain:
            by_domain[domain].sort(key=lambda r: r.confidence, reverse=True)
        return dict(by_domain)

    # ------------------------------------------------------------------
    # 生命周期：import / export / status
    # ------------------------------------------------------------------

    def import_yaml(self, yaml_path: str, project_id: str | None = None) -> int:
        """从 YAML 文件导入规则，返回加载数量。"""
        with open(yaml_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        rules = data.get("rules", []) if isinstance(data, dict) else data or []
        return self.add_rules_from_dicts(rules, project_id)

    def export_yaml(
        self,
        project_id: str | None = None,
        path: str | None = None,
        confidence_threshold: float = 0.0,
    ) -> str:
        """将有效规则导出为 YAML 字符串（可选写文件）。"""
        effective = self.get_effective(project_id) if project_id else dict(self._global)
        rules = [
            r.to_dict()
            for r in effective.values()
            if r.confidence >= confidence_threshold
        ]
        out = {"rules": rules}
        text = yaml.safe_dump(out, allow_unicode=True, default_flow_style=False)
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
        return text

    def status(self, project_id: str | None = None) -> dict[str, Any]:
        """返回规则库状态摘要：按领域分组 + 置信度条。"""
        by_domain = self.list_by_domain(project_id)
        summary = {}
        for domain, rules in by_domain.items():
            confs = [r.confidence for r in rules]
            # 置信度条（每格 0.1）
            bins = [0.0, 0.2, 0.4, 0.6, 0.8, 1.01]
            hist = [0] * (len(bins) - 1)
            for c in confs:
                for i in range(len(bins) - 1):
                    if bins[i] <= c < bins[i + 1]:
                        hist[i] += 1
                        break
            bar = "".join(str(h) if h else "-" for h in hist)
            summary[domain] = {
                "count": len(rules),
                "mean_confidence": float(np.mean(confs)),
                "confidence_bar": bar,
                "top_rules": [
                    {"id": r.id, "confidence": r.confidence, "trigger": r.trigger[:40]}
                    for r in rules[:3]
                ],
            }
        return summary

    # ------------------------------------------------------------------
    # trigger 匹配：对自然语言场景描述打分
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """简单分词：提取英文单词 + 中文字符序列。"""
        # 英文单词
        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        # 中文连续字符
        chinese = set(re.findall(r"[\u4e00-\u9fff]+", text))
        return words | chinese

    # 中英同义词映射（轻量，可扩展）
    _SYNONYM_MAP: dict[str, set[str]] = {
        "database": {"database", "数据库", "db", "数据"},
        "连接": {"connection", "conn", "链接", "database connection", "连接"},
        "泄漏": {"leak", "泄漏", "泄露"},
        "资源": {"resource", "资源"},
        "安全": {"safety", "secure", "安全"},
        "性能": {"performance", "perf", "性能"},
        "异步": {"async", "asynchronous", "异步"},
        "超时": {"timeout", "time-out", "超时"},
        "密码": {"password", "secret", "密钥", "密码"},
        "索引": {"index", "indexing", "索引"},
        "缓存": {"cache", "caching", "缓存"},
        "关闭": {"close", "closed", "关闭", "未关闭"},
        "代码": {"code", "代码"},
    }

    def _expand(self, token: str) -> set[str]:
        """返回 token 及其同义词集合。"""
        group = {token}
        for synonyms in self._SYNONYM_MAP.values():
            if token in synonyms:
                group.update(synonyms)
        return group

    def score_trigger(self, rule_trigger: str, scene: str) -> float:
        """对单条规则 trigger 与场景描述的匹配打分 [0, 1]。

        计分策略（改进版）：
        - 中英同义词映射扩展匹配词表
        - 规则 trigger 全部 token 均出现在 scene → 高分
        - 部分匹配 → 线性插值
        - 无匹配 → 0
        """
        rule_tokens = self._tokenize(rule_trigger)
        scene_tokens = self._tokenize(scene)
        if not rule_tokens:
            return 0.0
        # 同义词展开
        rule_expanded: set[str] = set()
        for t in rule_tokens:
            rule_expanded.update(self._expand(t))
        scene_expanded: set[str] = set()
        for t in scene_tokens:
            scene_expanded.update(self._expand(t))
        overlap = len(rule_expanded & scene_expanded)
        return float(overlap / len(rule_expanded))

    def match(
        self,
        scene: str,
        project_id: str | None = None,
        min_score: float = 0.3,
        domain_filter: str | None = None,
        top_k: int = 5,
    ) -> list[tuple[InstinctRule, float]]:
        """对场景描述打分，返回 top-k 匹配规则列表（分数 ≥ min_score）。"""
        effective = self.get_effective(project_id) if project_id else dict(self._global)
        scored = []
        for rule in effective.values():
            if domain_filter and rule.domain != domain_filter:
                continue
            s = self.score_trigger(rule.trigger, scene)
            if s >= min_score:
                scored.append((rule, s))
        scored.sort(key=lambda x: (x[1], x[0].confidence), reverse=True)
        return scored[:top_k]
