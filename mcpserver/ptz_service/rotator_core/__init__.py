"""天线云台「固件语义」底层库（卷130 实现；现役消费者是 ptz_service 本身）。

原 ``mcpserver/antenna_rotator/``（W130 完整实现）中的三件底层——
行协议（protocol）、安全环（safety）、链路抽象（transport）——被 ptz_service
的演进实现继续依赖。按「固件语义只有一份」的原则收编为本子包。

daemon / scan / tools 等会话层与工具面已被 ptz_service 取代，不再保留；
本 ``__init__`` 刻意不做 re-export（消费方直接 ``from .rotator_core import protocol``
或 ``from .rotator_core.transport import X``），避免把旧面重新暴露出去。

上游：卷129 ``hardware/antenna-rotator/``（运动规划 / AS5600 闭环 / 舵机 PTZ /
G 代码命令面）。
"""
