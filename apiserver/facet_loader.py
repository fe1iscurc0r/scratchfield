"""Facet 槽位宿主加载器（卷178-B，阶段一）。

设计来源：`docs/Facet槽位-设计-2026-09-29.md`
  - Facet = 「一个包含多面能力、宿主只激活所需」的槽位（域包改表单字段，Facet 改能力面）
  - manifest 增量块 `facets.panel`（无此块 = 无面板面，零迁移成本）
  - **激活条件与装配策略同源**（单一判定）：该 agent `enabled === true && available === true`
  - 硬件类包激活前跑声明式预检（`facets.panel.precheck`），**任一失败不激活且不静默**——
    返回结构化错误（facet id / 失败项 / 原因）

本模块只做阶段一（manifest + 加载器 + 演示）；渲染端（状态卡片/控制面板 UI）留阶段二。
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

FACET_KINDS = ("status-card", "control-panel")


@dataclass(frozen=True)
class PrecheckSpec:
    """声明式预检：命令存在性（command）或工具谓词（tool）。"""

    command: str = ""
    tool: str = ""
    label: str = ""


@dataclass(frozen=True)
class PanelSpec:
    kind: str
    component: str
    title: str = ""
    poll: dict[str, Any] = field(default_factory=dict)
    actions: tuple[dict[str, Any], ...] = ()
    precheck: PrecheckSpec | None = None


@dataclass(frozen=True)
class FacetRegistration:
    agent_name: str
    panel: PanelSpec
    manifest_path: str


class FacetActivationError(Exception):
    """预检/激活失败的结构化错误（不静默降级）。

    字段：agent / facet（panel id 恒为 'panel'，阶段一）/ failed_check / reason。
    """

    def __init__(self, agent: str, facet: str, failed_check: str, reason: str):
        self.agent = agent
        self.facet = facet
        self.failed_check = failed_check
        self.reason = reason
        super().__init__(f"[facet] {agent}.{facet} 激活失败：{failed_check} —— {reason}")

    def to_dict(self) -> dict[str, str]:
        return {"agent": self.agent, "facet": self.facet,
                "failed_check": self.failed_check, "reason": self.reason}


def _parse_panel(agent_name: str, raw: dict[str, Any]) -> PanelSpec:
    poll = raw.get("poll") or {}
    actions = tuple(a for a in (raw.get("actions") or []) if isinstance(a, dict))
    pc_raw = raw.get("precheck") or {}
    precheck = None
    if isinstance(pc_raw, dict) and (pc_raw.get("command") or pc_raw.get("tool")):
        precheck = PrecheckSpec(command=str(pc_raw.get("command") or ""),
                                tool=str(pc_raw.get("tool") or ""),
                                label=str(pc_raw.get("label") or ""))
    return PanelSpec(
        kind=str(raw.get("kind") or ""),
        component=str(raw.get("component") or ""),
        title=str(raw.get("title") or agent_name),
        poll=dict(poll) if isinstance(poll, dict) else {},
        actions=actions,
        precheck=precheck,
    )


class FacetRegistry:
    """扫描 manifest 的 facets 块 → 注册槽位 → 按需激活（预检先行）。"""

    def __init__(self, command_probe: Callable[[str], bool] | None = None):
        self._regs: dict[str, FacetRegistration] = {}
        # 命令探针可注入（测试用）；缺省用 shutil.which 等价实现
        self._command_probe = command_probe or self._default_command_probe

    @staticmethod
    def _default_command_probe(cmd: str) -> bool:
        import shutil
        return shutil.which(cmd) is not None

    # ---- 注册 ----

    def scan(self, root: str | Path) -> list[FacetRegistration]:
        """扫 mcpserver/**/agent-manifest.json 的 facets 块并注册（幂等：重复 id 抛错）。"""
        root = Path(root)
        added: list[FacetRegistration] = []
        for mf in sorted(root.glob("mcpserver/**/agent-manifest.json")):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            facets = data.get("facets")
            if not isinstance(facets, dict):
                continue
            panel_raw = facets.get("panel")
            if not isinstance(panel_raw, dict):
                continue
            agent = str(data.get("name") or mf.parent.name)
            panel = _parse_panel(agent, panel_raw)
            if agent in self._regs:
                raise ValueError(f"重复 facet 注册：agent {agent!r} 在 "
                                 f"{self._regs[agent].manifest_path} 与 {mf} 同时声明 facets.panel")
            reg = FacetRegistration(agent_name=agent, panel=panel, manifest_path=str(mf))
            self._regs[agent] = reg
            added.append(reg)
        return added

    def register(self, reg: FacetRegistration) -> None:
        """直接注册（测试/演示用）；重复 agent 抛 ValueError。"""
        if reg.agent_name in self._regs:
            raise ValueError(f"重复 facet 注册：agent {reg.agent_name!r}")
        self._regs[reg.agent_name] = reg

    @property
    def registrations(self) -> list[FacetRegistration]:
        return [self._regs[k] for k in sorted(self._regs)]

    def get(self, agent: str) -> FacetRegistration | None:
        return self._regs.get(agent)

    # ---- 激活 ----

    def activate(
        self,
        agent: str,
        *,
        enabled: bool,
        available: bool,
        tool_probe: Callable[[str], bool] | None = None,
    ) -> PanelSpec:
        """按需激活：装配同源判定 → 预检 → 挂载。

        激活条件（与装配策略同源，单一判定，见设计稿 §四.1）：
          enabled && available（来自 GET /mcp/services 的该 agent 状态）
        任一不满足 → FacetActivationError（结构化，宿主据此提示 disabled/unavailable 原因）。
        预检不过 → FacetActivationError（failed_check 指明是 command 还是 tool）。
        """
        reg = self._regs.get(agent)
        if reg is None:
            raise FacetActivationError(agent, "panel", "registration", "该 agent 未注册任何 facets")
        if not enabled:
            raise FacetActivationError(agent, "panel", "assembly",
                                       "装配策略未启用（disabled_reason 见 GET /mcp/assembly）")
        if not available:
            raise FacetActivationError(agent, "panel", "assembly",
                                       "能力不可用（unavailable_reason 见 GET /mcp/services）")

        pc = reg.panel.precheck
        if pc is not None:
            if pc.command:
                if not self._command_probe(pc.command):
                    raise FacetActivationError(agent, "panel", "precheck:command",
                                               f"命令 {pc.command!r} 不存在于本机 PATH")
            if pc.tool:
                probe = tool_probe or (lambda _t: False)
                if not probe(pc.tool):
                    raise FacetActivationError(agent, "panel", "precheck:tool",
                                               f"预检工具 {pc.tool!r} 未通过（未注册或调用失败）")
        return reg.panel


def load_registry(root: str | Path, command_probe: Callable[[str], bool] | None = None) -> FacetRegistry:
    """便捷入口：建注册表并扫描。"""
    reg = FacetRegistry(command_probe=command_probe)
    reg.scan(root)
    return reg


__all__ = [
    "FacetActivationError",
    "FacetRegistration",
    "FacetRegistry",
    "PanelSpec",
    "PrecheckSpec",
    "load_registry",
]
