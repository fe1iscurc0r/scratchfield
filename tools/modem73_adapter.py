"""W58-04 MODEM73 KISS TNC 适配器（radio_suite 数字模式新通道）

依据 docs/modem73-kiss-tnc-接入方案.md：把已存在的 `tools/modem73_kiss_bridge.py`
的 KISS 编解码逻辑封装成可加载适配器，暴露统一接口 encode_frame / decode_frame /
PTT 触发；检测 modem73 二进制/库是否可用，不可用则 mock 降级并显式标注（诚实降级）。

Hamlib/rigctl PTT 留桩（无真电台时返回降级状态）。
"""
from __future__ import annotations

import shutil

from modem73_kiss_bridge import kiss_decode_frame, kiss_encode_frame

__all__ = ["modem73_available", "Modem73Adapter"]


def modem73_available() -> bool:
    """检测 modem73 二进制是否在 PATH 中（库可用性同理）。"""
    return shutil.which("modem73") is not None


class Modem73Adapter:
    """radio_suite 的 MODEM73 数字模式适配器。"""

    def __init__(self, modem73_bin: str | None = None) -> None:
        # 显式给二进制路径 → 视为可用；否则按 PATH 检测
        self._available = bool(modem73_bin) or modem73_available()
        self.degraded = not self._available
        self.degraded_reason = "modem73 二进制/库不可用，mock 降级" if self.degraded else ""

    # ---------- 统一接口 ----------

    def encode_frame(self, payload: bytes, port: int = 0) -> bytes:
        """KISS 编码（与桥接脚本对齐）。"""
        return kiss_encode_frame(payload, port)

    def decode_frame(self, frame: bytes) -> tuple[int, bytes]:
        """KISS 解码，返回 (port, payload)。"""
        return kiss_decode_frame(frame)

    def ptt_trigger(self) -> bool:
        """PTT 键控（Hamlib/rigctl 桩）。降级态返回 False（不可键控）。"""
        return not self.degraded

    def status(self) -> dict:
        """适配器状态（供 radio_suite 状态面板）。"""
        return {
            "available": self._available,
            "degraded": self.degraded,
            "reason": self.degraded_reason,
        }
