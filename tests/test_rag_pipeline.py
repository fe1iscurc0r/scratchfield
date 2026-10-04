"""RAG 流水线冒烟测试

验证 RAGService 的核心流程：建临时 DB → 入库 md 文件 → query 命中 → delete → stats 归零。
直接调用 ``rag/rag_service.py`` 的 ``RAGService`` 类，不走 HTTP，使用 ``tmp_path`` fixture 确保测试隔离。

设计要点：
- 通过重置 ``RAGService`` 单例 + ``tmp_path`` 实现测试间完全隔离
- 注入 mock 嵌入引擎，避免依赖外部 bge 模型（torch/transformers）
- mock 返回固定归一化向量，保证 cosine 相似度恒为 1.0，使检索结果稳定可复现
- 不依赖后端服务、不依赖外部模型，可直接 ``pytest tests/test_rag_pipeline.py -v`` 运行
"""
import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from rag.rag_service import RAGService


def _make_mock_embedding_engine(dim: int = 384):
    """构造一个不依赖外部模型的 mock 嵌入引擎。

    所有文本返回同一个固定归一化向量，保证 query 与 chunk 的余弦相似度恒为 1.0，
    让冒烟测试聚焦于「流水线能否跑通」而非「语义相关性」。

    Args:
        dim: 嵌入维度，与 bge-small-zh-v1.5 默认维度保持一致（384）

    Returns:
        配置好的 MagicMock 嵌入引擎实例
    """
    engine = MagicMock()
    engine.is_available.return_value = False
    engine.get_device.return_value = "cpu"

    # 固定向量（归一化），用 RandomState 保证跨进程可复现
    fixed_vec = np.random.RandomState(42).randn(dim).astype(np.float32)
    fixed_vec = fixed_vec / np.linalg.norm(fixed_vec)

    def _encode(texts, batch_size: int = 32):
        """模拟 encode：每个文本返回同一固定向量。"""
        if not texts:
            return None
        return np.tile(fixed_vec, (len(texts), 1))

    engine.encode.side_effect = _encode
    return engine


@pytest.fixture
def rag_service(tmp_path):
    """构造一个使用临时 DB 的 RAGService 实例，测试间完全隔离。

    - 重置 ``RAGService._instance`` 单例，确保每个测试拿到全新实例
    - 用 ``tmp_path`` 隔离 DB 文件，避免污染用户数据目录
    - 注入 mock 嵌入引擎，避免依赖外部模型
    """
    # 重置单例，确保 __init__ 会重新执行
    RAGService._instance = None

    db_path = str(tmp_path / "test_rag.db")
    mock_engine = _make_mock_embedding_engine()

    # 在 RAGService 构造期间替换 get_embedding_engine，避免触发真实模型加载
    with patch("rag.rag_service.get_embedding_engine", return_value=mock_engine):
        service = RAGService(db_path=db_path)

    yield service

    # 清理：关闭 DB 连接并再次重置单例，避免影响后续测试
    service.close()
    RAGService._instance = None


@pytest.fixture
def sample_md_file(tmp_path) -> str:
    """生成一份用于入库的临时 markdown 文件（材料科研主题）。

    内容包含「壳聚糖」等关键词，便于后续检索命中验证。
    """
    md_path = tmp_path / "壳聚糖简介.md"
    md_path.write_text(
        "# 壳聚糖简介\n\n"
        "壳聚糖是一种天然高分子材料，由甲壳素脱乙酰化得到。\n"
        "具有良好的生物相容性和成膜性，广泛应用于生物医药领域。\n",
        encoding="utf-8",
    )
    return str(md_path)


class TestRAGPipeline:
    """RAG 流水线冒烟测试套件。"""

    def test_ingest_document_returns_success(self, rag_service, sample_md_file):
        """验证 markdown 文件能成功入库并返回 doc_id 与分块数。"""
        result = rag_service.ingest_document(sample_md_file, title="壳聚糖简介")

        assert result["success"] is True, f"入库失败: {result.get('error')}"
        assert "doc_id" in result, "返回结果缺少 doc_id"
        assert result["title"] == "壳聚糖简介"
        assert result["chunk_count"] >= 1, "分块数应至少为 1"

    def test_stats_reflects_ingested_document(self, rag_service, sample_md_file):
        """验证入库后统计信息正确反映文档数与分块数。"""
        rag_service.ingest_document(sample_md_file)
        stats = rag_service.get_stats()

        collection = stats["collections"]["materialscience"]
        assert collection["doc_count"] == 1, "入库后文档数应为 1"
        assert collection["chunk_count"] >= 1, "入库后分块数应至少为 1"

    def test_query_hits_ingested_document(self, rag_service, sample_md_file):
        """验证入库后用相关关键词能检索到该文档片段。

        使用 ``min_score=0.0`` 关闭分数过滤，确保 mock 嵌入下的冒烟测试稳定命中。
        """
        rag_service.ingest_document(sample_md_file)
        result = rag_service.query("壳聚糖", top_k=5, min_score=0.0)

        assert result["total_matches"] >= 1, "检索应命中至少 1 条"
        assert len(result["results"]) >= 1, "结果列表不应为空"
        assert "壳聚糖" in result["results"][0]["content"], "命中内容应包含查询关键词"

    def test_delete_document_clears_stats(self, rag_service, sample_md_file):
        """验证删除文档后统计信息归零。"""
        ingest_result = rag_service.ingest_document(sample_md_file)
        doc_id = ingest_result["doc_id"]

        delete_result = rag_service.delete_document(doc_id)
        assert delete_result["success"] is True, "删除应成功"

        stats = rag_service.get_stats()
        collection = stats["collections"]["materialscience"]
        assert collection["doc_count"] == 0, "删除后文档数应归零"
        assert collection["chunk_count"] == 0, "删除后分块数应归零"

    def test_full_pipeline_smoke(self, rag_service, sample_md_file):
        """端到端冒烟测试：入库 → 统计 → 检索 → 删除 → 统计归零。

        这是核心冒烟测试，验证 RAG 流水线的完整生命周期，
        任何一步失败都会阻断后续步骤，便于定位回归。
        """
        # Step 1: 入库 1 篇 md 文件
        ingest = rag_service.ingest_document(
            sample_md_file, tags=["材料", "高分子"]
        )
        assert ingest["success"] is True, f"入库失败: {ingest.get('error')}"
        doc_id = ingest["doc_id"]
        assert ingest["chunk_count"] >= 1

        # Step 2: 统计确认入库
        stats_after_ingest = rag_service.get_stats()
        assert (
            stats_after_ingest["collections"]["materialscience"]["doc_count"] == 1
        ), "入库后文档数应为 1"

        # Step 3: 检索命中
        query_result = rag_service.query("壳聚糖", top_k=5, min_score=0.0)
        assert query_result["total_matches"] >= 1, "检索未命中已入库文档"
        assert len(query_result["results"]) >= 1
        assert "壳聚糖" in query_result["results"][0]["content"]

        # Step 4: 删除文档
        delete_result = rag_service.delete_document(doc_id)
        assert delete_result["success"] is True, "删除应成功"

        # Step 5: 统计归零
        stats_after_delete = rag_service.get_stats()
        collection = stats_after_delete["collections"]["materialscience"]
        assert collection["doc_count"] == 0, "删除后文档数应归零"
        assert collection["chunk_count"] == 0, "删除后分块数应归零"

    def test_query_on_empty_db_returns_no_results(self, rag_service):
        """验证空库检索时返回空结果且不抛异常。"""
        result = rag_service.query("壳聚糖", top_k=5, min_score=0.0)
        assert result["total_matches"] == 0, "空库应无命中"
        assert result["results"] == [], "空库结果列表应为空"

    def test_delete_nonexistent_document_is_idempotent(self, rag_service):
        """验证删除不存在的 doc_id 时不会抛异常（幂等行为）。

        底层 VecDBClient.delete_document 对 SQLite DELETE 做了 try/except 包裹，
        删 0 行也视为成功（幂等），这里只验证不抛异常且统计仍归零。
        """
        result = rag_service.delete_document("doc_not_exist_12345")
        assert "success" in result, "删除接口应返回 success 字段"
        stats = rag_service.get_stats()
        assert stats["collections"]["materialscience"]["doc_count"] == 0
