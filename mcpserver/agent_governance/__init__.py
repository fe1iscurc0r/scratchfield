"""agent_governance —— 多 agent 身份-授权-审计三件套（工单 241）。

问题：scratchpad 的多 agent 协作没有身份-授权治理层 —— 任何 agent 调用另一个
agent 的能力时，无法证明「这条输出真由授权模型生成」。峰谷切换时上下文还会跨
provider（MiniMax-M3 / deepseek-flash）传递，没有任何签名/追溯机制。

三层骨架（各一层，互不耦合，可单独使用）：

| 层 | 模块 | 回答的问题 |
| --- | --- | --- |
| 身份证明 | `identity.py` | 这条输出**是谁、用哪个模型**产的、内容有没有被改过 |
| 授权令牌 | `authorization.py` | 这次调用**有没有被授权**，授权到什么时候 |
| 运行时审计 | `audit.py` | 所有调用**留下什么证据**，离线能不能查冒充/注入 |

接线层 `integration.py` 提供零侵入的 guard（默认旁路，环境变量开启）。
MCP agent 适配层 `governance.py` 把上述能力暴露成可被 `MCPManager.unified_call`
路由的工具。

⚠️ 工单原文写的落点是 ``core/agent_governance/``，但本仓根目录**没有** ``core/``
（全树 0 命中）。按仓内既有形态规范化落到 ``mcpserver/agent_governance/``，
与 ``mcpserver/agent_signing`` / ``agent_runtime`` 等同族并列，manifest 形态一致。
"""

from mcpserver.agent_governance.audit import (
    AUDIT_FILENAME,
    EVENT_AGENT_CALL,
    EVENT_RE_SIGN,
    EVENT_UNAUTHORIZED,
    count_events,
    read_events,
    record,
    record_unauthorized,
    resolve_audit_dir,
    resolve_audit_path,
    tail,
)
from mcpserver.agent_governance.authorization import (
    DEFAULT_TTL_S,
    AuthorizationAuthority,
    TokenClaims,
)
from mcpserver.agent_governance.errors import (
    E_AGENT_MISMATCH,
    E_BAD_SIGNATURE,
    E_CONTENT_MISMATCH,
    E_MALFORMED,
    E_MISSING_KEY,
    E_PROVIDER_MISMATCH,
    E_TOKEN_EXPIRED,
    E_TOKEN_MISSING,
    GovernanceError,
)
from mcpserver.agent_governance.identity import (
    ENV_ID_KEY,
    IdentitySigner,
    SignedOutput,
    content_digest,
)
from mcpserver.agent_governance.integration import (
    ENV_ENABLE,
    governance_enabled,
    guard_dispatch,
)

__version__ = "1.0.0"

__all__ = [
    "AUDIT_FILENAME",
    "DEFAULT_TTL_S",
    "E_AGENT_MISMATCH",
    "E_BAD_SIGNATURE",
    "E_CONTENT_MISMATCH",
    "E_MALFORMED",
    "E_MISSING_KEY",
    "E_PROVIDER_MISMATCH",
    "E_TOKEN_EXPIRED",
    "E_TOKEN_MISSING",
    "ENV_ENABLE",
    "ENV_ID_KEY",
    "EVENT_AGENT_CALL",
    "EVENT_RE_SIGN",
    "EVENT_UNAUTHORIZED",
    "AuthorizationAuthority",
    "GovernanceError",
    "IdentitySigner",
    "SignedOutput",
    "TokenClaims",
    "__version__",
    "content_digest",
    "count_events",
    "governance_enabled",
    "guard_dispatch",
    "read_events",
    "record",
    "record_unauthorized",
    "resolve_audit_dir",
    "resolve_audit_path",
    "tail",
]
