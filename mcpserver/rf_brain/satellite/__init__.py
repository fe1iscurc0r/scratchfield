"""rf_brain.satellite —— 卫星有效载荷解码（Y-05 · NOAA APT 等）。

本包与 decoders/ 解耦：APT 是成像型有效载荷（FM 解调后的 AM 副载波），
输出灰度图像而非文本/报文，故不进 decoders 注册表（decode_all 面向文本数字模式）。
"""
from __future__ import annotations

from . import apt  # noqa: F401

__all__ = ["apt"]
