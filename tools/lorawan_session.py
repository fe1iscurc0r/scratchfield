"""W71-11 · LoRaWAN 会话管理原型（吞入自 lorawan-server 思路，MIT 可吞）。

lorawan-server 的核心：OTAA 入网（Join）→ 会话（DevAddr + 会话密钥）→ 上行/下行路由。
本原型自研实现「会话注册 + 入网 + 路由 + 校验」的简化版（诚实标注：会话密钥用确定性
派生演示，非 LoRaWAN 真实 AES-128；真实密钥需按 LoRaWAN 规范用 AES 派生）。纯标准库。
"""
from __future__ import annotations

import hashlib


class SessionRegistry:
    """LoRaWAN 星型服务端的会话管理（简化，无真实 AES）。"""

    def __init__(self):
        self._sessions: dict[str, dict] = {}   # dev_eui -> session
        self._by_dev_addr: dict[str, str] = {}  # dev_addr -> dev_eui
        self._next_addr = 0x26000000

    def _derive_key(self, dev_eui: str, app_key: str, label: str) -> str:
        """确定性会话密钥派生（演示用，非 LoRaWAN AES-128）。"""
        return hashlib.sha256((dev_eui + app_key + label).encode()).hexdigest()[:16]

    def _alloc_dev_addr(self) -> str:
        addr = f"{self._next_addr:08X}"
        self._next_addr += 1
        return addr

    def join(self, dev_eui: str, app_key: str) -> dict:
        """OTAA 入网（简化）：分配 DevAddr + 派生 NwkSKey/AppSKey。"""
        if dev_eui in self._sessions:
            return self._sessions[dev_eui]
        dev_addr = self._alloc_dev_addr()
        session = {
            "dev_eui": dev_eui,
            "dev_addr": dev_addr,
            "nwk_skey": self._derive_key(dev_eui, app_key, "nwk"),
            "app_skey": self._derive_key(dev_eui, app_key, "app"),
        }
        self._sessions[dev_eui] = session
        self._by_dev_addr[dev_addr] = dev_eui
        return session

    def has_dev_addr(self, dev_addr: str) -> bool:
        return dev_addr in self._by_dev_addr

    def route_uplink(self, dev_addr: str, payload: str):
        """上行路由：DevAddr → 会话 → (dev_eui, payload)。未知 DevAddr 返回 None。"""
        if not self.has_dev_addr(dev_addr):
            return None
        return (self._by_dev_addr[dev_addr], payload)


def run_demo() -> None:
    reg = SessionRegistry()
    s = reg.join("DEV001", "APPKEY123")
    print(f"[W71-11] 入网: DevAddr={s['dev_addr']} NwkSKey={s['nwk_skey'][:6]}...")
    print(f"[W71-11] 上行路由: {reg.route_uplink(s['dev_addr'], 'payload-01')}")
    print(f"[W71-11] 未知 DevAddr 校验: {reg.route_uplink('DEADBEEF', 'x')}")


if __name__ == "__main__":
    run_demo()
