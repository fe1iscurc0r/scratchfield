"""记忆写入授权审计最小原型（P1-3 · W73-10 MutMem）。

依据 docs/memory-security-audit-评估.md：MutMem 的「加密授权记忆变异」——记忆
写入/变异需可验证授权，防篡改。对应 A216 记忆三阶段投毒剖面（写入/管理/检索）。

原型（纯 stdlib）：
  - MemoryWriteGate：HMAC 起源令牌校验（复用 A34 ROPE 起源门控思路）
  - 三阶段审计：write（写入校验）/ manage（变更校验）/ retrieve（读取溯源）
  - audit 流水记录每次写入的授权结果

安全类：只写防御。运行：python tools/memory_write_gate.py
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field


@dataclass
class MemoryWriteGate:
    """记忆写入授权门控：写入需有效起源令牌（HMAC），三阶段审计。"""

    secret: bytes
    store: dict[str, str] = field(default_factory=dict)
    audit: list[dict] = field(default_factory=list)

    def mint(self, key: str, value: str, source: str = "user") -> str:
        """用户/命名来源铸造写入令牌。"""
        return hmac.new(self.secret, f"{source}:{key}:{value}".encode(), hashlib.sha256).hexdigest()

    def _verify(self, key: str, value: str, source: str, token: str) -> bool:
        return hmac.compare_digest(self.mint(key, value, source), token)

    def write(self, key: str, value: str, source: str, token: str) -> bool:
        """写入（写入阶段校验）。"""
        ok = self._verify(key, value, source, token)
        if ok:
            self.store[key] = value
        self.audit.append({"stage": "write", "key": key, "authorized": ok})
        return ok

    def manage(self, key: str, value: str, source: str, token: str) -> bool:
        """变更（管理阶段校验，同样需授权）。"""
        return self.write(key, value, source, token)

    def retrieve(self, key: str) -> str | None:
        """读取（检索阶段：返回存值，审计记录读取溯源）。"""
        self.audit.append({"stage": "retrieve", "key": key, "authorized": True})
        return self.store.get(key)


if __name__ == "__main__":
    g = MemoryWriteGate(secret=b"mem-secret")
    tok = g.mint("k", "v", "user")
    print("[授权写入]", g.write("k", "v", "user", tok))
    print("[伪造写入]", g.write("k", "evil", "user", "0" * 64))
    print("[读取]", g.retrieve("k"))
    print("[审计]", g.audit)
