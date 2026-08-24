"""paper_miner — 论文实验参数自动提取器（靶子 A）。

职责：把论文（PDF/Markdown）中的实验参数（前驱体/交联剂/KOH 比例/碳化温度/
保温时间 → 导电率/比表面积/孔隙率/产率）提取为结构化 JSON 并入库 SQLite。

子模块：
- ollama_client: 最小 Ollama HTTP 客户端（Ollama 未装时优雅降级）
- db:          SQLite 实验库（stdlib sqlite3，零第三方依赖）
- extractor:   VLM 逐页解析 + LLM 参数提取 pipeline

Ollama 未安装/模型未拉取时，extractor 返回结构化错误，不崩溃。
"""
from __future__ import annotations

__all__ = [
    "ollama_client",
    "db",
    "extractor",
]

__version__ = "0.1.0"