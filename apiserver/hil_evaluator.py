"""HIL 边界评估模型（卷131 W131-02）。

把"等用户确认还是直接干"从硬编码变成可配置、可自学习的评估模型。
自研，语义参考 agent-spec（人类审查契约）/Pimsy（HIL 信任边界），不整抄。

设计要点（工单 W131-02）：
- eval_action(intent, params, context) → HILDecision {auto_approve, need_confirm, block}
- 决策因子（可配权重）：可逆性 + 影响范围 + 风险标签（manifest）+ 用户历史偏好
- HILDecision 带 confidence 和 reason
- 规则集外置 hil_rules.yaml/json，支持热重载
- 用户偏好学习只影响行为决策，不改变 LLM 输出内容（工单通用约束 3）
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 默认规则集（外置文件缺失时的兜底；与 hil_rules.json 同构）
DEFAULT_RULES: dict[str, Any] = {
    "version": 1,
    "weights": {
        # 决策因子权重：总分 = Σ(因子命中 × 权重)，正分倾向放行，负分倾向拦截
        "reversible_read": 2.0,      # 可逆（读/查）
        "irreversible_write": -2.0,  # 不可逆（写/删/执行）
        "scope_self": 1.0,           # 影响范围仅自己
        "scope_cross_system": -1.5,  # 跨系统影响
        "dangerous_tag": -10.0,      # manifest 风险标签 dangerous: true
        "irreversible_tag": -6.0,    # manifest 风险标签 irreversible: true
        "critical_tool": 0.0,        # critical 始终 need_confirm（单独逻辑，不走分）
        "user_preference": 2.5,      # 用户历史偏好（同类操作曾确认过）
    },
    "thresholds": {
        "auto_approve": 1.0,   # score >= 此值 → auto_approve
        "block": -4.0,         # score <= 此值 → block
        # 区间内 → need_confirm
    },
    "tool_rules": {
        # 读操作（默认 auto_approve 倾向）
        "file_read": {"reversible": True},
        "search": {"reversible": True},
        "query": {"reversible": True},
        # 写/删/执行（默认 need_confirm 倾向）
        "file_write": {"reversible": False},
        "file_edit": {"reversible": False},
        "exec": {"reversible": False},
        "bash": {"reversible": False},
        "delete": {"reversible": False},
    },
    "dangerous_tools": [],   # ["format_disk"] → block
    "critical_tools": [],    # ["send_email"] → 始终 need_confirm（与 W119-03 tool_gate 联动）
}

# 用户操作习惯的默认参数
_PREF_HALF_LIFE = 14 * 86400  # 偏好记录半衰期（14 天）——旧的确认记录逐渐失效


@dataclass
class HILDecision:
    """HIL 决策结果。"""
    action: str            # "auto_approve" | "need_confirm" | "block"
    confidence: float      # 0~1
    reason: str            # 人类可读理由（进审计日志）
    score: float = 0.0     # 决策因子总分（调试用）
    factors: dict = field(default_factory=dict)  # 命中的因子明细


def _default_prefs_path() -> Path:
    return Path.home() / ".lumo" / "hil_preferences.json"


class HILEvaluator:
    """HIL 边界评估器。

    用法：
        hil = HILEvaluator(rules_path="apiserver/hil_rules.json")
        d = hil.eval_action("file_write", {"path": "..."}, context={...})
        if d.action == "block": ...
    """

    def __init__(self, rules_path: str | Path | None = None,
                 prefs_path: str | Path | None = None):
        self._rules_path = Path(rules_path) if rules_path else None
        self._prefs_path = Path(prefs_path) if prefs_path else _default_prefs_path()
        self._rules: dict[str, Any] = dict(DEFAULT_RULES)
        self._rules_mtime: float = 0.0
        self._prefs: dict[str, dict] = {}   # {(tool_name, intent_class): {confirm_ts, count}}
        self._lock = threading.Lock()
        self._load_rules()
        self._load_prefs()

    # ---------- 规则集（热重载） ----------
    def _load_rules(self) -> None:
        if self._rules_path and self._rules_path.exists():
            try:
                raw = json.loads(self._rules_path.read_text(encoding="utf-8"))
                # 浅合并：外置文件覆盖默认（保留默认兜底）
                merged = dict(DEFAULT_RULES)
                merged.update(raw)
                self._rules = merged
                self._rules_mtime = self._rules_path.stat().st_mtime
            except (json.JSONDecodeError, OSError):
                # 规则文件损坏 → 用默认规则，不静默：reason 里会体现
                self._rules = dict(DEFAULT_RULES)

    def reload_if_changed(self) -> bool:
        """规则文件变更后热重载（返回是否重载了）。"""
        if not self._rules_path or not self._rules_path.exists():
            return False
        if self._rules_path.stat().st_mtime != self._rules_mtime:
            self._load_rules()
            return True
        return False

    # ---------- 用户偏好学习 ----------
    def _pref_key(self, intent: str, params: dict) -> tuple[str, str]:
        """偏好键：工具名 + 意图类（读/写/执行）——同类操作才有迁移性。"""
        rule = self._rules["tool_rules"].get(intent, {})
        ic = "read" if rule.get("reversible") else "write"
        return (intent, ic)

    def record_user_response(self, intent: str, params: dict, confirmed: bool) -> None:
        """记录用户对 need_confirm 的实际响应（confirmed=True 同意，False 拒绝）。

        工单 W131-02.4：下次同类操作调整权重。只影响行为决策不碰 LLM 输出。
        拒绝记录不产生负偏好（拒绝≠以后都自动拒绝——只是不学习）。
        """
        with self._lock:
            key = self._pref_key(intent, params)
            if confirmed:
                self._prefs[key] = {"ts": time.time(), "count": self._prefs.get(key, {}).get("count", 0) + 1}
                self._save_prefs()

    def _has_active_pref(self, intent: str, params: dict) -> bool:
        """同类操作曾被用户确认过，且记录未过半衰期。"""
        with self._lock:
            key = self._pref_key(intent, params)
            rec = self._prefs.get(key)
            if not rec:
                return False
            age = time.time() - rec.get("ts", 0)
            # 半衰衰减：14 天后权重减半，28 天后视为无偏好
            return age < _PREF_HALF_LIFE * 2

    def _load_prefs(self) -> None:
        try:
            if self._prefs_path.exists():
                data = json.loads(self._prefs_path.read_text(encoding="utf-8"))
                # JSON 的 tuple 键序列化成 "intent|class"
                self._prefs = {tuple(k.split("|", 1)): v for k, v in data.items()}
        except (json.JSONDecodeError, OSError):
            self._prefs = {}

    def _save_prefs(self) -> None:
        try:
            self._prefs_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"|".join(k): v for k, v in self._prefs.items()}
            self._prefs_path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass  # 偏好持久化失败不阻断决策（内存态仍有效）

    # ---------- 核心评估 ----------
    def eval_action(self, intent: str, params: dict | None = None,
                    context: dict | None = None) -> HILDecision:
        """评估一次工具/意图是否需要人工介入。

        intent: 工具名或意图标识（file_read/file_write/exec/...）
        params: 工具参数（影响范围判断用）
        context: 会话上下文（scope_hint: "self"|"cross_system" 等）
        """
        self.reload_if_changed()
        params = params or {}
        context = context or {}
        w = self._rules["weights"]
        th = self._rules["thresholds"]
        score = 0.0
        factors: dict[str, float] = {}

        # 危险工具 → 直接 block（不进打分）
        if intent in self._rules.get("dangerous_tools", []):
            return HILDecision("block", 1.0,
                               f"工具 {intent} 在 dangerous_tools 黑名单", -99.0,
                               {"dangerous_tools": w["dangerous_tag"]})

        # critical 工具 → 始终 need_confirm（与 W119-03 tool_gate 联动）
        if intent in self._rules.get("critical_tools", []):
            return HILDecision("need_confirm", 1.0,
                               f"工具 {intent} 标记 critical_tool，始终需确认",
                               0.0, {"critical_tool": 0.0})

        # 因子 1：可逆性（来自规则表 + manifest 风险标签可覆盖）
        rule = self._rules["tool_rules"].get(intent, {})
        reversible = bool(rule.get("reversible"))
        manifest_tags = self._manifest_tags(intent, context)
        if "dangerous" in manifest_tags:
            score += w["dangerous_tag"]; factors["dangerous_tag"] = w["dangerous_tag"]
            reversible = False
        if "irreversible" in manifest_tags:
            score += w["irreversible_tag"]; factors["irreversible_tag"] = w["irreversible_tag"]
            reversible = False
        if reversible:
            score += w["reversible_read"]; factors["reversible_read"] = w["reversible_read"]
        elif "irreversible_tag" not in factors:
            score += w["irreversible_write"]; factors["irreversible_write"] = w["irreversible_write"]

        # 因子 2：影响范围
        scope = context.get("scope_hint")
        if scope is None:
            # 自动推断：路径含仓外/系统目录 → 跨系统
            p = str(params.get("path", params.get("cwd", "")))
            scope = "cross_system" if p and (":" in p[:3] or p.startswith(("/", "~"))) else "self"
        if scope == "cross_system":
            score += w["scope_cross_system"]; factors["scope_cross_system"] = w["scope_cross_system"]
        else:
            score += w["scope_self"]; factors["scope_self"] = w["scope_self"]

        # 因子 3：用户历史偏好（同类操作曾确认 → 加分倾向自动）
        if self._has_active_pref(intent, params):
            score += w["user_preference"]; factors["user_preference"] = w["user_preference"]

        # 阈值判定
        if score >= th["auto_approve"]:
            action, conf = "auto_approve", min(1.0, 0.6 + score / 10)
        elif score <= th["block"]:
            action, conf = "block", min(1.0, 0.6 + abs(score) / 10)
        else:
            action, conf = "need_confirm", 0.7

        reason = f"score={score:.1f} factors={sorted(factors)}"
        return HILDecision(action, round(conf, 3), reason, round(score, 3), factors)

    @staticmethod
    def _manifest_tags(intent: str, context: dict) -> set[str]:
        """从 context 携带的工具 manifest 读风险标签（dangerous/irreversible）。"""
        manifest = context.get("tool_manifests", {}).get(intent, {})
        return set(manifest.get("tags", []) if isinstance(manifest, dict) else [])


# 进程级单例（apiserver 内共享）
_evaluator: HILEvaluator | None = None


_evaluator_lock = threading.Lock()


def get_hil_evaluator(rules_path: str | Path | None = None) -> HILEvaluator:
    global _evaluator
    if _evaluator is None:
        with _evaluator_lock:
            if _evaluator is None:
                _evaluator = HILEvaluator(rules_path)
    return _evaluator
