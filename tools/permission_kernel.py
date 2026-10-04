"""权限内核 + 运行时守卫最小原型（P1-2 · W73-08/12）。

依据 docs/agent-permission-guardrails-评估.md + docs/defense-as-skill-评估.md：
- Talos 权限内核：模型↔shell 之间加确定性权限最小化层，动作先过权限校验；
- Defense-as-Skill：运行时监控 skill 行为，恶意/未白名单动作被拦。

原型（纯 stdlib，无依赖）：
  - PermissionKernel：白名单 (skill, action)，allow() 确定性放行
  - RuntimeGuard：记录所有动作调用，未授权动作记入 violations（运行时守卫）

安全类：只写防御（拦截 + 审计），不写攻击代码。

运行：
  python tools/permission_kernel.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PermissionKernel:
    """确定性权限内核：模型动作先过白名单再达执行层。"""

    whitelist: set[tuple[str, str]] = field(default_factory=set)
    violations: list[dict] = field(default_factory=list)

    def allow(self, skill: str, action: str) -> bool:
        """确定性放行判定：仅白名单 (skill, action) 放行。"""
        return (skill, action) in self.whitelist

    def grant(self, skill: str, action: str) -> None:
        """登记白名单（权限最小化：按需显式授权）。"""
        self.whitelist.add((skill, action))

    def run(self, skill: str, action: str, fn) -> object | None:
        """运行时守卫：白名单动作才执行，否则记入 violations 并拒绝。"""
        if self.allow(skill, action):
            return fn()
        self.violations.append({"skill": skill, "action": action, "result": "denied"})
        return None


if __name__ == "__main__":
    kernel = PermissionKernel()
    kernel.grant("file_io", "read")
    print("[允许] file_io.read ->", kernel.run("file_io", "read", lambda: "ok"))
    print("[拒绝] shell.exec ->", kernel.run("shell", "exec", lambda: "BAD"))
    print("[violations]", kernel.violations)
