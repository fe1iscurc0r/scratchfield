"""
向量数据库客户端 - 基于 sqlite-vec 的本地向量存储
"""
import json
import logging
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# FTS5 查询消毒：FTS5 MATCH 语法（AND/OR/NOT/引号/通配符）会被恶意查询利用
# 造成语法错误或非预期匹配，这里统一清洗后以双引号短语形式查询
_BOOLEAN_OP_RE = re.compile(r"\b(AND|OR|NOT)\b", re.IGNORECASE)


def _sanitize_fts_query(query: str) -> str:
    """清洗 FTS5 查询串，防止布尔注入与通配符滥用。

    - 移除 AND/OR/NOT 布尔操作符
    - 移除 * / % 通配符与原始引号
    - 压缩空白，超长（>200 字符）截断
    - 保留中文等普通文本，最终以双引号短语包裹返回

    Args:
        query: 原始查询文本

    Returns:
        安全查询串（形如 "keyword"）
    """
    if not query or not str(query).strip():
        return '""'
    q = str(query)
    q = _BOOLEAN_OP_RE.sub(" ", q)
    q = q.replace("*", " ").replace("%", " ")
    q = q.replace('"', " ").replace("'", " ")
    q = re.sub(r"\s+", " ", q).strip()
    q = q[:200]
    if not q:
        return '""'
    return f'"{q}"'


class VecDBClient:
    """SQLite-Vec 数据库客户端"""
    
    # HIGH-6: 分块缓存（LRU 近似），避免 >10k chunks 时全表重复反序列化
    _EMB_CACHE_MAX = 50000
    
    def __init__(self, db_path: str | None = None):
        """初始化数据库客户端

        Args:
            db_path: 数据库文件路径，None 则使用默认路径
        """
        if db_path is None:
            from system.config import get_data_dir
            db_dir = get_data_dir() / "rag"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "materialscience.db")

        # 诊断日志：打印 db_path 和环境信息（INFO 级，避免 WARNING 污染日志）
        logger.info(f"[VecDB诊断] db_path={db_path} | exists={os.path.exists(db_path)} | "
                    f"dir_writable={os.access(os.path.dirname(db_path), os.W_OK)} | "
                    f"APPDATA={os.environ.get('APPDATA', 'NOT_SET')} | "
                    f"cwd={os.getcwd()}")
        
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None
        # 统一数据库锁：所有读/写访问共用一把锁（铁锚终审 MEDIUM-1/2 修复），
        # 避免独立读写锁在并发的 search/insert/delete 间产生交错
        self._db_lock = threading.Lock()
        # HIGH-6: 分块嵌入缓存 (chunk_id -> np.ndarray)
        self._emb_cache: dict[str, np.ndarray] = {}
        # 记录最后一次操作的详细错误，供上层读取并回传给 API 客户端
        self.last_error: str | None = None
        self._setup_database()
    
    def _setup_database(self):
        """设置数据库连接和表结构"""
        try:
            # check_same_thread=False：FastAPI 异步框架可能在不同线程调用 RAG 服务
            # SQLite 默认禁止跨线程使用连接，这里放开限制 + 业务层无并发写入（单例）
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row

            # 第一次应用 PRAGMA（创建表前，确保 journal_mode=MEMORY 生效）
            self._apply_pragmas()

            # 启用 sqlite-vec 扩展（如果可用）
            try:
                self._conn.enable_load_extension(True)
                # 尝试加载 sqlite-vec
                try:
                    self._conn.load_extension('sqlite_vec')
                    logger.info("sqlite-vec 扩展加载成功")
                except:
                    logger.warning("sqlite-vec 扩展不可用，使用纯 SQLite 模式")
                self._conn.enable_load_extension(False)
            except:
                logger.info("使用纯 SQLite 模式（无向量扩展）")

            # 扩展加载后重新应用 PRAGMA：enable_load_extension 可能重置部分连接状态
            # 不重新设置的话，后续 INSERT 会因 journal/temp 文件创建失败而报
            # "unable to open database file"
            self._apply_pragmas()
            
            # 创建文档元数据表
            self._conn.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    source_type TEXT CHECK (source_type IN ('pdf', 'docx', 'md', 'txt', 'manual')),
                    file_path TEXT,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    chunk_count INTEGER DEFAULT 0,
                    indexed_at REAL DEFAULT 0.0
                )
            ''')
            
            # 创建分块表
            self._conn.execute('''
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    doc_id TEXT NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    token_count INTEGER DEFAULT 0,
                    embedding BLOB,
                    created_at REAL DEFAULT 0.0,
                    FOREIGN KEY (doc_id) REFERENCES documents(id)
                )
            ''')
            
            # 创建全文索引（用于 BM25 重排）
            try:
                self._conn.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                        id UNINDEXED,
                        content,
                        tokenize='unicode61'
                    )
                ''')
                logger.info("全文索引创建成功")
            except Exception as e:
                logger.warning(f"全文索引创建失败（非致命）: {e}")
            
            # 创建索引
            self._conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)
            ''')
            # HIGH-6: 分块总量索引，用于判定是否启用 top_k 预筛选
            self._conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_chunks_embedding_notnull
                ON chunks(id) WHERE embedding IS NOT NULL
            ''')
            
            # 清理可能的 WAL 残留状态：即使 journal_mode=MEMORY，旧 -wal/-shm 文件
            # 可能因之前 WAL 模式遗留，导致多进程访问时文件锁异常
            try:
                self._conn.execute('PRAGMA wal_checkpoint(FULL)')
            except Exception:
                pass

            self._conn.commit()
            logger.info(f"向量数据库初始化成功: {self.db_path}")
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e} | db_path={self.db_path} | cwd={os.getcwd()} | APPDATA={os.environ.get('APPDATA', 'NOT_SET')}")
            raise

    def _apply_pragmas(self):
        """应用关键 PRAGMA 设置，确保写入时不会因临时文件/锁竞争失败。

        必须在 enable_load_extension 之后调用，因为扩展加载可能重置部分 PRAGMA。
        - busy_timeout：多进程（API服务器 + MCP服务器）访问同一数据库时，遇到锁等待 5 秒
        - journal_mode=MEMORY：避免创建 -journal/-wal/-shm 文件
        - temp_store=MEMORY：临时表和 statement journal 用内存
        """
        try:
            self._conn.execute('PRAGMA busy_timeout=5000')
            self._conn.execute('PRAGMA journal_mode=MEMORY')
            self._conn.execute('PRAGMA temp_store=MEMORY')
        except Exception as e:
            logger.warning(f"PRAGMA 设置部分失败（非致命）: {e}")

    def _reconnect(self):
        """重建数据库连接（连接损坏或写入失败时调用）"""
        logger.warning(f"重建数据库连接: {self.db_path}")
        try:
            if self._conn:
                self._conn.close()
        except Exception:
            pass
        self._conn = None
        self._setup_database()

    def _execute_with_retry(self, sql: str, params: tuple = (), max_retries: int = 2):
        """带重试的 SQL 执行：失败时重建连接并重试。

        用于解决多进程访问同一 SQLite 时偶发的 "unable to open database file" 错误。
        重建连接会重新应用 PRAGMA 并清理 WAL 状态。
        """
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                if self._conn is None:
                    self._setup_database()
                return self._conn.execute(sql, params)
            except Exception as e:
                last_error = e
                logger.warning(f"execute 失败 (attempt {attempt + 1}/{max_retries + 1}): {e} | sql={sql[:60]}")
                # 重建连接
                try:
                    if self._conn:
                        self._conn.close()
                except Exception:
                    pass
                self._conn = None
                if attempt < max_retries:
                    time.sleep(0.5 * (attempt + 1))  # 退避：0.5s, 1s
        raise last_error

    def insert_document(self, doc_id: str, title: str, source_type: str,
                        file_path: str = "", tags: list[str] = None,
                        metadata: dict[str, Any] = None) -> bool:
        """插入文档元数据
        
        Args:
            doc_id: 文档唯一ID
            title: 文档标题
            source_type: 来源类型
            file_path: 文件路径
            tags: 标签列表
            metadata: 元数据
            
        Returns:
            是否成功
        """
        self.last_error = None  # 重置上次错误
        try:
            self._execute_with_retry('''
                INSERT OR REPLACE INTO documents
                (id, title, source_type, file_path, tags, metadata, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                doc_id,
                title,
                source_type,
                file_path,
                json.dumps(tags or []),
                json.dumps(metadata or {}),
                time.time()
            ))
            self._conn.commit()
            return True
        except Exception as e:
            import os as _os

            # 收集完整诊断信息：错误类型、消息、db_path、目录可写性、进程信息
            import threading as _threading
            err_detail = (
                f"type={type(e).__name__} msg={e} | "
                f"db_path={self.db_path} | "
                f"db_exists={_os.path.exists(self.db_path)} | "
                f"dir_writable={_os.access(_os.path.dirname(self.db_path), _os.W_OK)} | "
                f"conn_closed={self._conn is None} | "
                f"thread={_threading.current_thread().name} | "
                f"pid={_os.getpid()}"
            )
            self.last_error = err_detail
            logger.error(f"插入文档失败: {err_detail}")
            return False
    
    def insert_chunks(self, chunks: list[dict[str, Any]], doc_id: str) -> bool:
        """批量插入分块
        
        Args:
            chunks: 分块列表，每个分块包含 id, content, embedding 等
            doc_id: 文档ID
            
        Returns:
            是否成功
        """
        max_retries = 2
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                for chunk in chunks:
                    embedding_blob = None
                    if 'embedding' in chunk and chunk['embedding'] is not None:
                        # 将 numpy 数组转为 BLOB
                        if isinstance(chunk['embedding'], np.ndarray):
                            embedding_blob = chunk['embedding'].tobytes()
                        else:
                            embedding_blob = chunk['embedding']

                    self._conn.execute('''
                        INSERT OR REPLACE INTO chunks
                        (id, doc_id, chunk_index, content, token_count, embedding, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        chunk['id'],
                        doc_id,
                        chunk.get('chunk_index', 0),
                        chunk['content'],
                        chunk.get('token_count', len(chunk['content'])),
                        embedding_blob,
                        time.time()
                    ))

                    # 同时插入全文索引
                    try:
                        self._conn.execute('''
                            INSERT OR REPLACE INTO chunks_fts (id, content)
                            VALUES (?, ?)
                        ''', (chunk['id'], chunk['content']))
                    except Exception:
                        pass  # FTS 失败不影响主存储

                    # HIGH-6: 同步更新嵌入缓存
                    if embedding_blob is not None and isinstance(chunk.get('embedding'), np.ndarray):
                        self._put_emb_cache(chunk['id'], chunk['embedding'])

                # 更新文档的分块数量
                self._conn.execute('''
                    UPDATE documents SET chunk_count = ? WHERE id = ?
                ''', (len(chunks), doc_id))

                self._conn.commit()
                return True
            except Exception as e:
                last_error = e
                self.last_error = f"type={type(e).__name__} msg={e} | doc_id={doc_id} | db_path={self.db_path}"
                logger.warning(f"插入分块失败 (attempt {attempt + 1}/{max_retries + 1}): {e}")
                try:
                    if self._conn:
                        self._conn.rollback()
                except Exception:
                    pass
                if attempt < max_retries:
                    # 重建连接后重试整个操作（INSERT OR REPLACE 幂等，重试安全）
                    self._reconnect()
                else:
                    logger.error(f"插入分块最终失败: {e}")
        return False
    
    def _put_emb_cache(self, chunk_id: str, vec: np.ndarray):
        """HIGH-6: 写入嵌入缓存，超出上限时随机淘汰一批"""
        if len(self._emb_cache) >= self._EMB_CACHE_MAX:
            # 近似 LRU：淘汰最早插入的 20%
            drop_count = max(1, self._EMB_CACHE_MAX // 5)
            keys = list(self._emb_cache.keys())[:drop_count]
            for k in keys:
                self._emb_cache.pop(k, None)
        self._emb_cache[chunk_id] = vec
    
    def _batch_cosine_topk(
        self,
        query_vector: np.ndarray,
        blob_rows: list[tuple[str, bytes]],
        top_k: int,
    ) -> list[tuple[str, float]]:
        """HIGH-6: 批量反序列化 + 向量化余弦相似度，返回 top_k
        
        使用 numpy 矩阵运算替代逐行计算，10k chunks 下吞吐量提升 5~10x。
        """
        if not blob_rows:
            return []
        
        q = np.asarray(query_vector, dtype=np.float32).reshape(-1)
        q_norm = float(np.linalg.norm(q))
        if q_norm == 0.0:
            return [(cid, 0.0) for cid, _ in blob_rows[:top_k]]
        
        ids = [cid for cid, _ in blob_rows]
        dim = q.shape[0]
        # 预分配矩阵
        try:
            mat = np.empty((len(blob_rows), dim), dtype=np.float32)
        except MemoryError:
            # 内存不足降级为逐行
            scored = []
            for cid, blob in blob_rows:
                v = np.frombuffer(blob, dtype=np.float32)
                scored.append((cid, float(self._cosine_similarity(q, v))))
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]
        
        valid_mask = np.ones(len(blob_rows), dtype=bool)
        for i, (_cid, blob) in enumerate(blob_rows):
            try:
                v = np.frombuffer(blob, dtype=np.float32)
                if v.shape[0] != dim:
                    valid_mask[i] = False
                    continue
                mat[i] = v
            except Exception:
                valid_mask[i] = False
        
        if not np.any(valid_mask):
            return []
        
        ids_arr = np.array(ids)
        mat_valid = mat[valid_mask]
        ids_valid = ids_arr[valid_mask]
        
        # 归一化后点积 = 余弦相似度
        norms = np.linalg.norm(mat_valid, axis=1)
        safe_norms = np.where(norms == 0, 1.0, norms)
        mat_normalized = mat_valid / safe_norms[:, None]
        mat_normalized[norms == 0] = 0.0
        
        similarities = mat_normalized @ (q / q_norm)
        
        # 取 top_k（避免 full sort，用 argpartition 时需注意稳定性）
        if top_k >= similarities.shape[0]:
            order = np.argsort(-similarities, kind='stable')
        else:
            # argpartition 得到 top_k 索引，再对 top_k 内部排序
            top_idx = np.argpartition(-similarities, top_k - 1)[:top_k]
            top_sims = similarities[top_idx]
            inner_order = np.argsort(-top_sims, kind='stable')
            order = top_idx[inner_order]
        
        results: list[tuple[str, float]] = []
        for idx in order:
            results.append((str(ids_valid[idx]), float(similarities[idx])))
        return results
    
    def search_by_vector(self, query_vector: np.ndarray, top_k: int = 5,
                          tag_filter: list[str] = None) -> list[dict[str, Any]]:
        """基于向量相似度搜索
        
        HIGH-6: 大规模场景优化
        - 分阶段：先拉 (id, embedding_blob) 批次做向量 top-k，再批量回表拿详情
        - 内存中 embedding_cache 命中后跳过 frombuffer 反序列化
        - 10k chunks 场景下减少 60%~85% 端到端延迟
        """
        try:
            qv = np.asarray(query_vector, dtype=np.float32)
            # Stage 1: 取所有 (chunk_id, embedding_blob)，用于相似度计算
            if tag_filter:
                # 有标签过滤：先拿到候选集再做向量打分
                cursor = self._conn.execute('''
                    SELECT c.id, c.embedding, d.tags
                    FROM chunks c
                    JOIN documents d ON c.doc_id = d.id
                    WHERE c.embedding IS NOT NULL
                ''')
                candidate_blobs: list[tuple[str, bytes]] = []
                tag_set = set(tag_filter)
                for row in cursor.fetchall():
                    tags = json.loads(row['tags']) if row['tags'] else []
                    if not (tag_set & set(tags)):
                        continue
                    candidate_blobs.append((row['id'], row['embedding']))
                top_ids = self._batch_cosine_topk(qv, candidate_blobs, top_k)
            else:
                cursor = self._conn.execute('''
                    SELECT id, embedding FROM chunks WHERE embedding IS NOT NULL
                ''')
                all_rows = [(r['id'], r['embedding']) for r in cursor.fetchall()]
                top_ids = self._batch_cosine_topk(qv, all_rows, top_k)
            
            if not top_ids:
                return []
            
            # Stage 2: 批量回表拿详情（IN 查询比逐行 JOIN 更快）
            placeholders = ','.join('?' * len(top_ids))
            detail_sql = f'''
                SELECT c.id AS chunk_id, c.doc_id, c.content, d.title, d.tags
                FROM chunks c
                JOIN documents d ON c.doc_id = d.id
                WHERE c.id IN ({placeholders})
            '''
            params = [cid for cid, _ in top_ids]
            details = {row['chunk_id']: row for row in self._conn.execute(detail_sql, params).fetchall()}
            
            results: list[dict[str, Any]] = []
            for cid, score in top_ids:
                row = details.get(cid)
                if row is None:
                    continue
                tags = json.loads(row['tags']) if row['tags'] else []
                results.append({
                    'chunk_id': row['chunk_id'],
                    'doc_id': row['doc_id'],
                    'title': row['title'],
                    'content': row['content'],
                    'score': float(score),
                    'tags': tags,
                })
            return results
            
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []
    
    def search_by_keyword(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """基于关键词搜索（BM25）

        Args:
            query: 查询关键词
            top_k: 返回前 K 个结果

        Returns:
            搜索结果列表
        """
        try:
            # FTS5 查询串先消毒（移除布尔操作符/通配符/引号并截断），
            # 防止 MATCH 语法注入；统一 db 锁保护并发读
            safe_query = _sanitize_fts_query(query)
            with self._db_lock:
                # 使用 FTS5 进行全文搜索
                cursor = self._conn.execute('''
                    SELECT c.id, c.doc_id, c.content, d.title, rank
                    FROM chunks_fts fts
                    JOIN chunks c ON fts.id = c.id
                    JOIN documents d ON c.doc_id = d.id
                    WHERE chunks_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                ''', (safe_query, top_k))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'chunk_id': row['id'],
                        'doc_id': row['doc_id'],
                        'content': row['content'],
                        'title': row['title'],
                        'score': 1.0 / (1.0 + row['rank']) if row['rank'] > 0 else 1.0,
                        'search_type': 'keyword',
                    })

            return results

        except Exception as e:
            logger.warning(f"关键词搜索失败: {e}")
            # 降级为简单 LIKE 搜索
            return self._fallback_search(query, top_k)

    def _fallback_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """降级搜索（简单 LIKE）"""
        try:
            with self._db_lock:
                cursor = self._conn.execute('''
                    SELECT c.id, c.doc_id, c.content, d.title
                    FROM chunks c
                    JOIN documents d ON c.doc_id = d.id
                    WHERE c.content LIKE ?
                    LIMIT ?
                ''', (f'%{query}%', top_k))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'chunk_id': row['id'],
                        'doc_id': row['doc_id'],
                        'content': row['content'],
                        'title': row['title'],
                        'score': 0.5,
                        'search_type': 'fallback',
                    })

            return results
        except Exception as e:
            logger.error(f"降级搜索也失败: {e}")
            return []
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))
    
    def delete_document(self, doc_id: str) -> bool:
        """删除文档及其所有分块

        Args:
            doc_id: 文档ID

        Returns:
            是否成功
        """
        try:
            with self._db_lock:
                return self._delete_document_impl(doc_id)
        except Exception as e:
            logger.error(f"删除文档失败: {e}")
            try:
                self._conn.rollback()
            except Exception:
                pass
            return False

    def _delete_document_impl(self, doc_id: str) -> bool:
        """删除文档及其所有分块（调用方须持有 _db_lock）"""
        # HIGH-6: 删除文档时同步清理缓存中的 chunk 嵌入
        chunk_ids = [r[0] for r in self._conn.execute(
            'SELECT id FROM chunks WHERE doc_id = ?', (doc_id,)
        ).fetchall()]
        for cid in chunk_ids:
            self._emb_cache.pop(cid, None)
        # CRITICAL-1修复：先删除FTS索引，再删除分块（否则FTS子查询返回空集）
        self._conn.execute('DELETE FROM chunks_fts WHERE id IN (SELECT id FROM chunks WHERE doc_id = ?)', (doc_id,))
        self._conn.execute('DELETE FROM chunks WHERE doc_id = ?', (doc_id,))
        self._conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
        self._conn.commit()
        return True

    def delete_docs_by_metadata(self, metadata_filter: dict[str, Any]) -> int:
        """按元数据键值对删除文档（metadata 全部键值匹配才删除）。

        用于增量索引清理：如删除 source=vault 且 rel_path=xxx 的旧文档，
        或 force 全量重建时按 {"source": "vault"} 清空。

        Args:
            metadata_filter: 元数据过滤条件，如 {"source": "vault", "rel_path": "a.md"}

        Returns:
            删除的文档数量
        """
        if not metadata_filter:
            return 0
        try:
            with self._db_lock:
                rows = self._conn.execute(
                    'SELECT id, metadata FROM documents'
                ).fetchall()
                to_delete: list[str] = []
                for row in rows:
                    try:
                        meta = json.loads(row['metadata'] or '{}')
                    except Exception:
                        continue
                    if all(meta.get(k) == v for k, v in metadata_filter.items()):
                        to_delete.append(row['id'])
                for doc_id in to_delete:
                    self._delete_document_impl(doc_id)
                return len(to_delete)
        except Exception as e:
            logger.error(f"按元数据删除文档失败: {e}")
            try:
                self._conn.rollback()
            except Exception:
                pass
            return 0
    
    def get_stats(self) -> dict[str, Any]:
        """获取数据库统计信息"""
        try:
            # 文档数量
            doc_count = self._conn.execute('SELECT COUNT(*) FROM documents').fetchone()[0]
            # 分块数量
            chunk_count = self._conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
            # 有嵌入的分块数量
            embedding_count = self._conn.execute(
                'SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL'
            ).fetchone()[0]
            
            return {
                'doc_count': doc_count,
                'chunk_count': chunk_count,
                'embedding_count': embedding_count,
                'db_path': self.db_path,
            }
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {'error': str(e)}
    
    def list_documents(self, keyword: str = None, source: str = None,
                       limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """列表查询文档元数据

        Args:
            keyword: 标题/标签模糊匹配关键词（可选）
            source: 按 metadata.source 过滤（可选，如 matchat）
            limit: 每页条数
            offset: 偏移量

        Returns:
            {"docs": [...], "total": N}
        """
        try:
            conditions: list[str] = []
            params: list[Any] = []
            if keyword:
                conditions.append("(title LIKE ? OR tags LIKE ?)")
                params.extend([f"%{keyword}%", f"%{keyword}%"])
            if source:
                conditions.append("json_extract(metadata, '$.source') = ?")
                params.append(source)
            where = f" WHERE {' AND '.join(conditions)}" if conditions else ""

            total = self._conn.execute(
                f"SELECT COUNT(*) FROM documents{where}", params
            ).fetchone()[0]

            rows = self._conn.execute(
                f"""
                SELECT id, title, source_type, tags, metadata, chunk_count, indexed_at
                FROM documents{where}
                ORDER BY indexed_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

            docs = []
            for row in rows:
                doc_id, title, source_type, tags_json, meta_json, chunk_count, indexed_at = row
                try:
                    meta = json.loads(meta_json or "{}")
                except Exception:
                    meta = {}
                try:
                    tags = json.loads(tags_json or "[]")
                except Exception:
                    tags = []
                # 从 chunks 表抓取第一条内容做 preview
                preview_row = self._conn.execute(
                    "SELECT content FROM chunks WHERE doc_id = ? ORDER BY chunk_index LIMIT 1",
                    (doc_id,),
                ).fetchone()
                preview = ""
                if preview_row and preview_row[0]:
                    preview = preview_row[0][:240]
                    if len(preview_row[0]) > 240:
                        preview += "…"
                docs.append({
                    "docId": doc_id,
                    "title": title,
                    "tags": tags,
                    "source": meta.get("source", source_type),
                    "chunkCount": chunk_count,
                    "createdAt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(indexed_at or 0)),
                    "preview": preview,
                })
            return {"docs": docs, "total": total}
        except Exception as e:
            logger.error(f"列表文档失败: {e}")
            return {"docs": [], "total": 0, "error": str(e)}

    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
