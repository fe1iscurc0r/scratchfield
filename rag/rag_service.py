"""
RAG 服务模块 - 材料科研知识检索服务
"""
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.chunk_splitter import ChunkSplitter
from rag.document_parser import DocumentParser
from rag.embedding_engine import EmbeddingEngine, get_embedding_engine
from rag.vecdb_client import VecDBClient

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 服务单例 - 提供文档入库、检索等功能"""
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        # HIGH-5: 双检锁单例模式，线程安全
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        
        self._vec_db = VecDBClient(db_path)
        self._embedding_engine = get_embedding_engine()
        self._chunk_splitter = ChunkSplitter(chunk_size=512, overlap=50)
        self._parser = DocumentParser()
        self._initialized = True
        
        logger.info("RAG 服务初始化完成")
    
    def ingest_document(self, file_path: str, title: str = None,
                        tags: list[str] = None, metadata: dict[str, Any] = None) -> dict[str, Any]:
        """文档入库
        
        Args:
            file_path: 文件路径
            title: 文档标题（可选，默认使用文件名）
            tags: 标签列表
            metadata: 元数据
            
        Returns:
            入库结果
        """
        try:
            start_time = time.time()
            path = Path(file_path)
            
            # 生成文档ID
            doc_id = f"doc_{uuid.uuid4().hex[:8]}"
            
            # 使用文件名作为默认标题
            if title is None:
                title = path.stem
            
            # 解析文档
            logger.info(f"正在解析文档: {file_path}")
            text = self._parser.parse(file_path)
            if text is None:
                logger.warning("文档解析失败，文件路径已脱敏")
                return {'success': False, 'error': '文档解析失败，请检查文件格式'}
            
            # 判断来源类型
            suffix = path.suffix.lower()
            source_type = suffix.lstrip('.')
            if source_type == 'doc':
                source_type = 'docx'
            elif source_type == 'markdown':
                source_type = 'md'
            elif source_type not in ('pdf', 'docx', 'md', 'txt'):
                source_type = 'manual'
            
            # 保存原始文件副本
            self._save_document_copy(file_path, doc_id)
            
            # 分块
            logger.info(f"正在分块: {len(text)} 字符")
            chunks = self._chunk_splitter.split(text, metadata={'doc_id': doc_id})
            
            if not chunks:
                return {'success': False, 'error': '文档分块为空'}
            
            # 为每个块生成ID并准备嵌入
            chunk_texts = [c['content'] for c in chunks]
            chunk_ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
            
            # 生成嵌入
            logger.info(f"正在生成嵌入向量: {len(chunks)} 个块")
            embeddings = self._embedding_engine.encode(chunk_texts)
            
            # HIGH-2 修复：嵌入失败不注入随机向量（种子 42 的随机向量会让检索"看起来正常"但结果完全无意义）
            # 改为 fail-fast：向上层抛出错误，调用方应提示用户检查嵌入模型/网络
            if embeddings is None:
                msg = "嵌入生成失败（模型未加载或编码异常），请检查嵌入引擎后重试。"
                logger.error(msg)
                return {'success': False, 'error': msg}
            
            if len(embeddings) != len(chunks):
                logger.error(f"嵌入数量({len(embeddings)})与分块数量({len(chunks)})不匹配")
                return {'success': False, 'error': '嵌入生成数量不匹配，请重试'}
            
            # 准备分块数据
            chunk_data_list = []
            for i, (chunk_id, chunk, embedding) in enumerate(zip(chunk_ids, chunks, embeddings)):
                chunk_data = {
                    'id': chunk_id,
                    'chunk_index': i,
                    'content': chunk['content'],
                    'token_count': chunk.get('token_count', len(chunk['content'])),
                    'embedding': embedding,
                }
                chunk_data_list.append(chunk_data)
            
            # 存入数据库
            success = self._vec_db.insert_document(
                doc_id=doc_id,
                title=title,
                source_type=source_type,
                file_path=file_path,
                tags=tags,
                metadata=metadata
            )
            
            if not success:
                # 读取 vec_db 的详细错误信息，传递给上层 API，便于排查
                db_err = getattr(self._vec_db, 'last_error', None) or 'unknown'
                logger.error(f"insert_document 失败: doc_id={doc_id} | detail={db_err}")
                return {
                    'success': False,
                    'error': '保存文档元数据失败',
                    # detail 仅本地诊断用，不直接回传给前端（避免泄露路径）
                    'detail': db_err,
                }
            
            success = self._vec_db.insert_chunks(chunk_data_list, doc_id)
            if not success:
                db_err = getattr(self._vec_db, 'last_error', None) or 'unknown'
                logger.error(f"insert_chunks 失败: doc_id={doc_id} | detail={db_err}")
                return {
                    'success': False,
                    'error': '保存分块数据失败',
                    'detail': db_err,
                }
            
            elapsed = time.time() - start_time
            result = {
                'success': True,
                'doc_id': doc_id,
                'title': title,
                'chunk_count': len(chunks),
                'tags': tags or [],
                'indexed_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'elapsed_ms': int(elapsed * 1000),
                'fallback': not self._embedding_engine.is_available(),
            }
            
            logger.info(f"文档入库成功: {doc_id}, {len(chunks)} 个块, 耗时 {elapsed:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"文档入库失败: {e}")
            return {'success': False, 'error': '文档入库失败，请稍后重试'}
    
    def query(self, query_text: str, top_k: int = 5,
              tags: list[str] = None, min_score: float = 0.6,
              rerank: bool = True) -> dict[str, Any]:
        """知识检索
        
        Args:
            query_text: 查询文本
            top_k: 返回前 K 个结果
            tags: 标签过滤
            min_score: 最低分数阈值
            rerank: 是否启用重排序
            
        Returns:
            检索结果
        """
        try:
            start_time = time.time()
            
            # 生成查询向量
            query_embedding = self._embedding_engine.encode([query_text])

            # MEDIUM-2 修复：双路 RRF 融合（倒数排名融合），替代 if-else 二选一
            # 向量检索总能提供语义命中，关键词检索总能提供字面精准命中；
            # 一路缺失不阻断，两路都有则用 RRF(k=60) 合并：score += 1/(k+rank)
            fetch_k = top_k * 3 if rerank else top_k * 2

            vec_results: list[dict] = []
            kw_results: list[dict] = []

            if query_embedding is not None:
                vec_results = self._vec_db.search_by_vector(
                    query_vector=query_embedding[0],
                    top_k=fetch_k,
                    tag_filter=tags
                )
            else:
                logger.warning("嵌入引擎不可用，跳过向量检索（仅用关键词）")

            try:
                kw_results = self._vec_db.search_by_keyword(query_text, top_k=fetch_k)
            except Exception as e:
                logger.warning(f"关键词检索异常，跳过关键词路: {e}")
                kw_results = []

            results = self._rrf_fuse(vec_results, kw_results, top_k=fetch_k)
            
            # 重排序（可选）
            if rerank and len(results) > top_k:
                results = self._rerank_results(results, query_text)
            
            # 过滤低分结果
            filtered_results = [r for r in results if r.get('score', 0) >= min_score]
            
            # 截取前 K 个
            final_results = filtered_results[:top_k]
            
            elapsed = time.time() - start_time
            
            return {
                'query_id': f'q_{uuid.uuid4().hex[:8]}',
                'results': final_results,
                'total_matches': len(results),
                'latency_ms': int(elapsed * 1000),
            }
            
        except Exception as e:
            logger.error(f"检索失败: {e}")
            return {'query_id': '', 'results': [], 'total_matches': 0, 'error': '检索服务暂不可用，请稍后重试'}
    
    def delete_document(self, doc_id: str) -> dict[str, Any]:
        """删除文档
        
        Args:
            doc_id: 文档ID
            
        Returns:
            删除结果
        """
        try:
            success = self._vec_db.delete_document(doc_id)
            if success:
                return {'success': True, 'doc_id': doc_id}
            else:
                return {'success': False, 'error': '删除失败'}
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            return {'success': False, 'error': '删除文档失败，请稍后重试'}

    def delete_by_metadata(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """按元数据键值对删除文档（metadata 全部键值匹配才删除）。

        供 VaultIndexer 增量索引清理使用：如 force 全量重建时按
        {"source": "vault"} 清空，或按 {"source": "vault", "rel_path": rel} 删除单文件旧数据。

        Args:
            metadata: 元数据过滤条件

        Returns:
            删除结果
        """
        try:
            count = self._vec_db.delete_docs_by_metadata(metadata or {})
            return {'success': True, 'deleted': count}
        except Exception as e:
            logger.error(f"按元数据删除文档失败: {e}")
            return {'success': False, 'error': '删除文档失败，请稍后重试'}
    
    def get_stats(self) -> dict[str, Any]:
        """获取 RAG 统计信息"""
        db_stats = self._vec_db.get_stats()
        engine_available = self._embedding_engine.is_available()
        
        return {
            'collections': {
                'materialscience': {
                    'doc_count': db_stats.get('doc_count', 0),
                    'chunk_count': db_stats.get('chunk_count', 0),
                    'embedding_model': 'BAAI/bge-small-zh-v1.5',
                    'embedding_count': db_stats.get('embedding_count', 0),
                }
            },
            'embedding_device': self._embedding_engine.get_device(),
            'embedding_available': engine_available,
            'fallback_mode': not engine_available,
            'supported_formats': DocumentParser.get_supported_formats(),
        }
    
    def list_documents(self, keyword: str = None, source: str = None,
                       limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """列表查询知识库文档"""
        try:
            return self._vec_db.list_documents(keyword, source, limit, offset)
        except Exception as e:
            logger.error(f"列表文档失败: {e}")
            return {"docs": [], "total": 0, "error": str(e)}

    def _save_document_copy(self, file_path: str, doc_id: str):
        """保存文档副本到数据目录"""
        try:
            from system.config import get_data_dir
            doc_dir = get_data_dir() / "rag" / "documents"
            doc_dir.mkdir(parents=True, exist_ok=True)
            
            src_path = Path(file_path)
            if src_path.exists():
                dst_path = doc_dir / f"{doc_id}{src_path.suffix}"
                import shutil
                shutil.copy2(file_path, str(dst_path))
        except Exception as e:
            logger.warning(f"保存文档副本失败（非致命）: {e}")
    
    def _rrf_fuse(self, vec_results: list[dict], kw_results: list[dict],
                  top_k: int = 50, k_const: int = 60) -> list[dict]:
        """MEDIUM-2：倒数排名融合（Reciprocal Rank Fusion）
        - 用排序位次而非绝对分数合并，解决两路线性刻度不一致问题
        - 任何一路缺失都自动降级为另一路排序，不会空结果
        """
        fused: dict[str, dict] = {}

        for ranked_list in (vec_results, kw_results):
            for rank, r in enumerate(ranked_list):
                cid = r.get('chunk_id') or r.get('id')
                if not cid:
                    continue
                if cid not in fused:
                    fused[cid] = {
                        **r,  # 先展开原始记录字段（包括 score）
                        # 再用 RRF 归一化字段覆盖：score 从 0 开始累加，丢弃原始 cosine/BM25 绝对分
                        'score': 0.0,
                        'vec_rank': None,
                        'kw_rank': None,
                    }
                fused[cid]['score'] += 1.0 / (k_const + rank + 1)
                if ranked_list is vec_results:
                    fused[cid]['vec_rank'] = rank + 1
                else:
                    fused[cid]['kw_rank'] = rank + 1

        merged = sorted(fused.values(), key=lambda x: x['score'], reverse=True)
        # 归一化：RRF 原始分（≈ 1/(k+rank)）与调用方 min_score(0~1) 量纲不匹配，
        # 不归一化时阈值过滤会恒返空。除以实际最大分使第一名=1.0，
        # min_score 语义变为“相对第一名的分数比例”；原始分保留在 rrf_raw
        if merged:
            max_raw = merged[0]['score'] or 1.0
            for r in merged:
                r['rrf_raw'] = r['score']
                r['score'] = r['score'] / max_raw
        return merged[:top_k]

    def _extract_ngram_tokens(self, text: str, max_n: int = 3) -> set:
        """HIGH-1：为中文提取 1/2/3-gram 字符切片 + 标点分词，替代单字符集合。
        例："壳聚糖用途" → {'壳','聚','糖','用','途','壳聚','聚糖','糖用','用途','壳聚糖','聚糖用','糖用途','壳聚糖用途'}
        这样"壳聚糖"命中不会因含"糖"而把含糖无关文档排到前面。
        """
        import re
        t = re.sub(r'\s+', '', text.lower())
        if not t:
            return set()
        tokens = set()
        for n in range(1, max_n + 1):
            for i in range(len(t) - n + 1):
                gram = t[i:i + n]
                tokens.add(gram)
        return tokens

    def _rerank_results(self, results: list[dict], query: str) -> list[dict]:
        """HIGH-1：重排序改用 query n-gram 在 content 中的连续子串命中数加权，
        不再使用单字符集合覆盖率（会因"壳聚糖"拆成{'壳','聚','糖'}误排含糖文档）。
        """
        query_tokens = self._extract_ngram_tokens(query)
        if not query_tokens:
            return results

        for result in results:
            content = result.get('content', '').lower()
            content_tokens = self._extract_ngram_tokens(content)
            if not content_tokens:
                continue

            # 按 token 长度加权：长 n-gram 命中更有区分度（1字=1, 2字=4, 3字=9）
            hit_score = 0.0
            query_total = 0.0
            for qt in query_tokens:
                n = len(qt)
                weight = float(n * n)
                query_total += weight
                if qt in content_tokens:
                    hit_score += weight
            coverage = hit_score / max(query_total, 1e-9)

            original_score = result.get('score', 0)
            result['score'] = original_score * 0.7 + coverage * 0.3
            result['rerank_score'] = coverage

        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results
    
    def close(self):
        """关闭服务"""
        self._vec_db.close()
        logger.info("RAG 服务已关闭")


def get_rag_service() -> RAGService:
    """获取全局 RAG 服务实例"""
    return RAGService()
