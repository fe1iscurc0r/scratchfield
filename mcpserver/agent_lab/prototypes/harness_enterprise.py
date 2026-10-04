"""A48 · Harness Paradigm Enterprise 企业级 Harness 原型（来源 2608.20622）

论文核心：企业 LLM Agent at Scale——harness 作为企业基础设施而非工具，
凭证作用域（credential scoping）+ 授权逻辑是安全规模化的关键。

原型：
  - Credential：{主体, 作用域集合, 过期时间}
  - PolicyEngine：动作→所需作用域映射，最小权限检查 + 过期检查 + 审计留痕
  - Harness：基础设施门面，所有工具调用必须过凭证作用域闸口
评估：放行/拒绝决策矩阵全部正确；越权请求被拒且留审计。

运行：python -m mcpserver.agent_lab.prototypes.harness_enterprise
"""
from __future__ import annotations

from dataclasses import dataclass

# 动作 → 所需作用域（授权逻辑的核心映射）
ACTION_SCOPES = {
    "read_doc": "docs.read",
    "write_doc": "docs.write",
    "deploy": "ops.deploy",
    "read_secret": "secrets.read",
}


@dataclass(frozen=True)
class Credential:
    """凭证：主体 + 作用域集合 + 过期时刻（最小权限原则载体）"""
    principal: str
    scopes: frozenset
    expires_at: float = float("inf")


class PolicyEngine:
    """授权引擎：三重检查（动作已知 / 未过期 / 作用域覆盖），全程审计留痕"""

    def __init__(self) -> None:
        self.audit: list[dict] = []

    def check(self, cred: Credential, action: str, now: float = 0.0
              ) -> tuple[bool, str]:
        need = ACTION_SCOPES.get(action)
        if need is None:
            ok, reason = False, "未知动作"
        elif now > cred.expires_at:
            ok, reason = False, "凭证过期"
        elif need not in cred.scopes:
            ok, reason = False, "作用域不足"
        else:
            ok, reason = True, "放行"
        self.audit.append(dict(principal=cred.principal, action=action,
                               allow=ok, reason=reason))
        return ok, reason


class Harness:
    """harness = 企业基础设施层：一切工具调用强制经过凭证作用域闸口"""

    def __init__(self, engine: PolicyEngine):
        self.engine = engine

    def invoke(self, cred: Credential, action: str, now: float = 0.0) -> dict:
        ok, reason = self.engine.check(cred, action, now=now)
        if not ok:
            return dict(blocked=True, reason=reason)
        return dict(blocked=False, result=f"{action} 已执行")


def evaluate() -> dict:
    """决策矩阵：四类场景（放行/作用域不足/过期/未知动作）全覆盖"""
    h = Harness(PolicyEngine())
    reader = Credential("agent-a", frozenset({"docs.read"}))
    ops = Credential("agent-b", frozenset({"ops.deploy", "docs.read"}), expires_at=10.0)
    cases = [
        (reader, "read_doc", 0.0, False),    # 期望放行
        (reader, "write_doc", 0.0, True),    # 期望拦截（作用域不足）
        (ops, "deploy", 20.0, True),         # 期望拦截（凭证过期）
        (ops, "deploy", 5.0, False),         # 期望放行（未过期且作用域覆盖）
        (reader, "read_secret", 0.0, True),  # 期望拦截（作用域不足）
        (reader, "drop_table", 0.0, True),   # 期望拦截（未知动作）
    ]
    wrong = 0
    for cred, action, now, expect_blocked in cases:
        out = h.invoke(cred, action, now=now)
        if out["blocked"] != expect_blocked:
            wrong += 1
    return dict(n_cases=len(cases), wrong=wrong,
                audit_len=len(h.engine.audit))


if __name__ == "__main__":
    r = evaluate()
    print(f"Harness 企业授权：{r['n_cases']} 例决策矩阵，错判 {r['wrong']}，"
          f"审计记录 {r['audit_len']} 条")
