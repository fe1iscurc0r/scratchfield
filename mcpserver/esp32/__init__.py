"""ESP32 / LoRa 传感网仿真底座（工单 243 · 漏斗 2.0 轻量猎手第 3 单）。

子模块
------
- ``cluster_sim`` : **节点空间分簇模拟器** —— RSSI 可达图上的「阈值 + 跳数」聚类，
  输出簇健康度与不稳定链路（纯几何 + 图算法，不烧硬件）。
- ``rlnc``        : RLNC 编解码**兼容层** —— 真值源在 ``mcpserver/rf_brain/rlnc/``，
  本包只做 re-export + 工单字面 API 封装，**不含独立数学实现**（理由见该包 ``encoder.py``）。
- ``dashboard``   : 弹性曲线（失活率 → 数据重建成功率）+ 簇规模/跳数权衡 → ``dashboard.json``
  （**只产数据，不画前端**）。

分层口径（勿混用）
------------------
本包关心**节点的空间可达性**；``mcpserver/rf_brain/rlnc/`` 关心**链路的可靠度分档**
（EWMA 丢包估计 → high/mid/low → 编码冗余率）。两者可串联、不可互相替代，详见
``cluster_sim/cluster.py`` 顶部说明。
"""
from __future__ import annotations

__all__ = ["cluster_sim", "dashboard", "rlnc"]
