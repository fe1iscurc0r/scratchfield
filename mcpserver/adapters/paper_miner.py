"""paper_miner MCP 适配层（论文实验参数提取器，靶子 A）。

暴露工具：
- extract_paper(path): 提取单篇论文实验参数并入库 papers.db
- query_experiments(...): 按条件查询实验库（供陆墨自然语言查询）
- paper_miner_status(): 依赖/库状态

依赖 Ollama（VLM minicpm-v:8b + LLM llama3.2:3b）。Ollama 未装时
healthcheck 返回 False，门禁自动跳过，不影响全局。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from mcpserver.adapters._common import register_capability_safe
from mcpserver.paper_miner import db as _pdb
from mcpserver.paper_miner import extractor as _extractor
from mcpserver.paper_miner.ollama_client import healthcheck as _ollama_healthcheck

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.environ.get("PAPER_DB_PATH", str(Path(__file__).resolve().parents[2] / "papers.db"))

CAPABILITY: dict = {
    "name": "paper_miner",
    "displayName": "论文实验参数提取器",
    "description": "从论文 PDF/Markdown 提取前驱体/KOH/碳化温度等实验参数并入库 SQLite，支持查询。",
    "version": "0.1.0",
    "license": "MIT",
    "vendor": "scratchpad/paper_miner",
    "degradation_mode": "skip-if-ollama-missing",
    "_from_adapter": "paper_miner",
}


def healthcheck() -> bool:
    """paper_miner 依赖 Ollama + LLM 模型可用。"""
    hc = _ollama_healthcheck()
    if not hc["ok"]:
        logger.warning("[adapter:paper_miner] Ollama 不可用，跳过: %s", hc.get("error"))
        return False
    models = hc.get("models", [])
    if not any(_extractor.LLM_MODEL in m for m in models):
        logger.warning(
            "[adapter:paper_miner] Ollama 缺模型 %s（已拉: %s），跳过",
            _extractor.LLM_MODEL, models,
        )
        return False
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """注册论文提取与查询工具。"""

    def _get_db() -> _pdb.ExperimentDB:
        return _pdb.init_db(_DEFAULT_DB)

    async def extract_paper(path: str) -> dict:
        """提取单篇论文实验参数并写入 papers.db。

        Args:
            path: 论文绝对路径（.md 走 LLM 路径；.pdf 走 VLM+LLM 路径）
        """
        db = _get_db()
        try:
            return _extractor.extract_paper(path, db=db)
        finally:
            db.close()

    async def query_experiments(
        precursor: str | None = None,
        min_temp: float | None = None,
        min_conductivity: float | None = None,
        limit: int = 50,
    ) -> dict:
        """查询实验库，如"木质素水凝胶里戊二醛交联、碳化温度>800、导电率>10 的"。

        Args:
            precursor: 前驱体关键词（如 木质素/秸秆/戊二醛）
            min_temp: 最小碳化温度 °C
            min_conductivity: 最小导电率 S/cm
            limit: 最大返回条数
        """
        db = _get_db()
        try:
            rows = db.query_experiments(
                precursor=precursor,
                min_temp=min_temp,
                min_conductivity=min_conductivity,
                limit=limit,
            )
            return {"ok": True, "count": len(rows), "experiments": rows}
        finally:
            db.close()

    async def paper_miner_status() -> dict:
        """paper_miner 运行状态（Ollama / 模型 / 库记录数）。"""
        hc = _ollama_healthcheck()
        db = _get_db()
        try:
            count = db.count()
        finally:
            db.close()
        return {
            "ok": True,
            "ollama": hc,
            "llm_model": _extractor.LLM_MODEL,
            "vlm_model": _extractor.VLM_MODEL,
            "db_path": _DEFAULT_DB,
            "db_records": count,
        }

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(extract_paper, name="extract_paper")
        mcp_server.add_tool(query_experiments, name="query_experiments")
        mcp_server.add_tool(paper_miner_status, name="paper_miner_status")

    register_capability_safe(mcp_registry, CAPABILITY)