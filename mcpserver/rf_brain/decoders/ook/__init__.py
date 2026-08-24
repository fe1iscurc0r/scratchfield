"""OOK 解码器子包（哨兵网格 N-02）

输入是 SX1278 OOK 模式解调出的「脉冲宽度序列」（微秒），不是 IQ 样本——
这是 OOK 解码器与 Phase6 现有 IQ 解码器（aprs/psk31/dtfm/pocsag）的本质区别。

对外纯函数：
- pulse_demod: 脉冲分类 / bit 拼装 / 奇偶校验工具
- acurite: Acurite Tower + 515 解码（字段完整，温度待真机校准）
- lacrosse: LaCrosse TX141TH-Bv2 骨架（字段待校准，不编造）

注册：本包不主动注册进 IQ registry（输入语义不同）。由上层
sentinel_bridge（N-04）按需调用 decode_acurite / decode_lacrosse。
"""
from __future__ import annotations

from . import acurite, lacrosse, pulse_demod  # noqa: F401
from .acurite import decode_acurite
from .lacrosse import decode_lacrosse

__all__ = [
    "decode_acurite",
    "decode_lacrosse",
    "acurite",
    "lacrosse",
    "pulse_demod",
]
