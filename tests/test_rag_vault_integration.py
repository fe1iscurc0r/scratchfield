"""
混合 RAG + Vault 索引 验证测试

验证场景：
1. VaultIndexer 扫描 + 增量索引逻辑
2. _sanitize_fts_query 防注入
3. 混合 RAG 双路召回（GRAG + 本地向量）
4. 铁锚审查修复点：原子写入、线程安全、速率限制
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# 将 scratchpad 加入 path
_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR))


class TestVaultIndexer(unittest.TestCase):
    """测试 VaultIndexer 核心逻辑"""

    def setUp(self):
        from rag.vault_indexer import VaultIndexer
        self.cls = VaultIndexer

    def test_scan_files_ignores_hidden(self):
        """扫描应跳过 . 开头的隐藏目录和文件"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            # 正常文件
            (root / "note1.md").write_text("内容1", encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "note2.md").write_text("内容2", encoding="utf-8")
            # 隐藏目录和文件
            (root / ".obsidian").mkdir()
            (root / ".obsidian" / "config.md").write_text("配置", encoding="utf-8")
            (root / ".hidden.md").write_text("隐藏", encoding="utf-8")
            # 非 md 文件
            (root / "data.txt").write_text("其他", encoding="utf-8")

            idx = self.cls(vault_dir=tmpdir)
            files = idx.scan_files()
            # scan_files 现返回 (file_path, source, rel_path) 元组，取 file_path
            names = [f[0].name for f in files]

            self.assertIn("note1.md", names)
            self.assertIn("note2.md", names)
            self.assertNotIn("config.md", names)  # 隐藏目录下的
            self.assertNotIn(".hidden.md", names)  # 隐藏文件
            self.assertNotIn("data.txt", names)  # 非 md

    def test_compute_hash_detects_changes(self):
        """哈希应在文件变更后产生不同值"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "test.md"
            fp.write_text("hello v1", encoding="utf-8")

            idx = self.cls(vault_dir=tmpdir)
            h1 = idx._compute_hash(fp)

            fp.write_text("hello v2", encoding="utf-8")
            h2 = idx._compute_hash(fp)

            self.assertNotEqual(h1, h2)
            self.assertEqual(len(h1), 16)

    def test_get_changed_files_identifies_new(self):
        """新增文件应出现在 to_index 列表"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fp = Path(tmpdir) / "new.md"
            fp.write_text("新笔记", encoding="utf-8")

            idx = self.cls(vault_dir=tmpdir)
            to_index, deleted, total = idx.get_changed_files()

            self.assertEqual(len(to_index), 1)
            self.assertEqual(len(deleted), 0)
            self.assertEqual(total, 1)
            # to_index 元素为 (fp, source, state_key, hash_val)；state_key 形如 "vault:new.md"
            self.assertIn("new.md", to_index[0][2])

    def test_atomic_save_state(self):
        """_save_state 应使用原子写入（临时文件 + rename）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = self.cls(vault_dir=tmpdir)
            idx._indexed_hashes = {"test.md": "abc123"}
            idx._save_state()

            state_file = Path(tmpdir) / ".vault_index_state.json"
            self.assertTrue(state_file.exists())

            # 不应残留 .tmp 文件
            tmp_files = list(Path(tmpdir).glob("*.tmp"))
            self.assertEqual(len(tmp_files), 0)

            # 验证内容
            content = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual(content["test.md"], "abc123")

    def test_get_indexed_count_public(self):
        """get_indexed_count 公开方法应返回正确计数"""
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = self.cls(vault_dir=tmpdir)
            self.assertEqual(idx.get_indexed_count(), 0)
            idx._indexed_hashes = {"a.md": "1", "b.md": "2"}
            self.assertEqual(idx.get_indexed_count(), 2)


class TestFTS5Sanitizer(unittest.TestCase):
    """测试 FTS5 查询消毒"""

    def setUp(self):
        from rag.vecdb_client import _sanitize_fts_query
        self.fn = _sanitize_fts_query

    def test_removes_boolean_operators(self):
        """应移除 AND/OR/NOT 布尔运算符"""
        result = self.fn("python AND java NOT javascript")
        self.assertNotIn(" AND ", result)
        self.assertNotIn(" NOT ", result)
        self.assertIn('"', result)  # 双引号包裹

    def test_removes_wildcard(self):
        """应移除 * 通配符"""
        result = self.fn("test*")
        self.assertNotIn("*", result)

    def test_removes_quotes(self):
        """应移除原始双引号"""
        result = self.fn('"injected"')
        # 结果应被双引号包裹，但内部不应有额外双引号
        self.assertEqual(result.count('"'), 2)

    def test_truncates_long_query(self):
        """超长查询应被截断"""
        long_query = "测试" * 100  # 300 字符
        result = self.fn(long_query)
        # 去除首尾双引号后应 <= 200 字符
        inner = result[1:-1] if result.startswith('"') else result
        self.assertLessEqual(len(inner), 200)

    def test_preserves_chinese_text(self):
        """正常中文输入应被保留"""
        result = self.fn("机器学习算法")
        self.assertIn("机器学习算法", result)


class TestSingletonThreadSafety(unittest.TestCase):
    """测试 VaultIndexer 单例线程安全"""

    def test_double_checked_lock(self):
        """get_vault_indexer 应使用双重检查锁定"""
        import inspect

        from rag.vault_indexer import _indexer_lock, get_vault_indexer

        # 检查锁存在
        self.assertIsInstance(_indexer_lock, type(threading.Lock()))

        # 多线程首次调用应只创建一个实例
        instances = []
        lock = threading.Lock()

        def call_getter():
            inst = get_vault_indexer()
            with lock:
                instances.append(inst)

        threads = [threading.Thread(target=call_getter) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应获得同一个实例
        self.assertEqual(len(set(id(i) for i in instances)), 1)


class TestForceIndexRateLimit(unittest.TestCase):
    """测试强制索引速率限制"""

    def test_rate_limit_logic(self):
        """验证速率限制变量和常量存在"""
        import apiserver.routes.rag as rag_route
        # 检查速率限制常量
        self.assertTrue(hasattr(rag_route, 'FORCE_MIN_INTERVAL'))
        self.assertEqual(rag_route.FORCE_MIN_INTERVAL, 60)
        self.assertTrue(hasattr(rag_route, '_last_force_index'))


class TestVaultStatusEndpoint(unittest.TestCase):
    """测试 /vault/status 端点脱敏"""

    def test_status_uses_public_method(self):
        """vault_status 应使用 get_indexed_count() 而非直接访问 _indexed_hashes"""
        import inspect

        from apiserver.routes import rag as rag_route

        source = inspect.getsource(rag_route.vault_status)
        # 不应直接访问 _indexed_hashes
        self.assertNotIn("_indexed_hashes", source)
        # 应使用公开方法
        self.assertIn("get_indexed_count()", source)
        # 应脱敏路径
        self.assertIn(".name", source)


class TestLumoProxyMixedRAG(unittest.TestCase):
    """测试 lumo_proxy 混合 RAG 召回"""

    def test_query_local_rag_has_timeout(self):
        """_query_local_rag 应使用 asyncio.wait_for 超时保护"""
        import inspect

        from apiserver.routes import lumo_proxy

        source = inspect.getsource(lumo_proxy._query_local_rag)
        self.assertIn("wait_for", source)
        self.assertIn("run_in_executor", source)

    def test_query_grag_has_truncation(self):
        """_query_grag 返回内容应有长度截断"""
        import inspect

        from apiserver.routes import lumo_proxy

        source = inspect.getsource(lumo_proxy._query_grag)
        self.assertIn("2000", source)  # 截断阈值
        self.assertIn("truncated", source)

    def test_query_grag_catches_timeout(self):
        """_query_grag 应捕获 asyncio.TimeoutError"""
        import inspect

        from apiserver.routes import lumo_proxy

        source = inspect.getsource(lumo_proxy._query_grag)
        self.assertIn("TimeoutError", source)

    def test_log_levels_are_warning(self):
        """RAG 降级日志级别应为 warning 而非 debug"""
        import inspect

        from apiserver.routes import lumo_proxy

        source = inspect.getsource(lumo_proxy)
        # 检查关键降级日志使用 warning
        self.assertIn("logger.warning", source)


class TestVaultIndexStartup(unittest.TestCase):
    """测试 API 启动时 Vault 索引为后台任务"""

    def test_bg_index_function_exists(self):
        """_bg_index_vault 函数应存在"""
        from apiserver.api_server import _bg_index_vault
        self.assertTrue(callable(_bg_index_vault))

    def test_lifespan_uses_create_task(self):
        """lifespan 应使用 create_task 启动后台索引"""
        import inspect

        from apiserver import api_server

        source = inspect.getsource(api_server.lifespan)
        self.assertIn("create_task", source)
        self.assertIn("to_thread", source)

    def test_lifespan_saves_task_ref(self):
        """lifespan 应保存 task 引用防止 GC"""
        import inspect

        from apiserver import api_server

        source = inspect.getsource(api_server.lifespan)
        self.assertIn("app.state", source)


class TestParallelRecall(unittest.TestCase):
    """测试双路并行召回（沈遥终审③修复）"""

    def test_uses_asyncio_gather(self):
        """_query_rag_standalone 应使用 asyncio.gather 真正并行"""
        import inspect

        from apiserver.routes import lumo_proxy

        source = inspect.getsource(lumo_proxy._query_rag_standalone)
        self.assertIn("asyncio.gather", source)
        self.assertIn("return_exceptions=True", source)

    def test_no_messages_param(self):
        """_query_rag_standalone 签名不应有 messages 参数"""
        import inspect

        from apiserver.routes import lumo_proxy

        sig = inspect.signature(lumo_proxy._query_rag_standalone)
        self.assertNotIn("messages", sig.parameters)


class TestStaleDataCleanup(unittest.TestCase):
    """测试增量索引旧数据清理（沈遥终审①修复）"""

    def test_delete_by_metadata_exists(self):
        """RAGService 应有 delete_by_metadata 方法"""
        from rag.rag_service import RAGService
        self.assertTrue(hasattr(RAGService, 'delete_by_metadata'))

    def test_vecdb_delete_by_metadata_exists(self):
        """VecDBClient 应有 delete_docs_by_metadata 方法"""
        from rag.vecdb_client import VecDBClient
        self.assertTrue(hasattr(VecDBClient, 'delete_docs_by_metadata'))

    def test_index_vault_deletes_before_ingest(self):
        """index_vault 应在 ingest 前删除旧文档"""
        import inspect

        from rag.vault_indexer import VaultIndexer

        source = inspect.getsource(VaultIndexer.index_vault)
        self.assertIn("delete_by_metadata", source)
        self.assertIn("rel_path", source)

    def test_force_mode_cleans_all_vault(self):
        """force 模式应删除所有 source=vault 的文档"""
        import inspect

        from rag.vault_indexer import VaultIndexer

        source = inspect.getsource(VaultIndexer.index_vault)
        # force 块中应按 source=vault 删除
        self.assertIn('"source"', source)
        self.assertIn('"vault"', source)


class TestStateLock(unittest.TestCase):
    """测试 VaultIndexer 状态锁（沈遥终审④修复）"""

    def test_state_lock_exists(self):
        """VaultIndexer 应有 _state_lock"""
        with tempfile.TemporaryDirectory() as tmpdir:
            from rag.vault_indexer import VaultIndexer
            idx = VaultIndexer(vault_dir=tmpdir)
            self.assertTrue(hasattr(idx, '_state_lock'))

    def test_get_indexed_count_thread_safe(self):
        """get_indexed_count 应使用 _state_lock"""
        import inspect

        from rag.vault_indexer import VaultIndexer

        source = inspect.getsource(VaultIndexer.get_indexed_count)
        self.assertIn("_state_lock", source)


class TestStatsSkippedCalculation(unittest.TestCase):
    """测试 stats[skipped] 计算正确性（沈遥终审②修复）"""

    def test_skipped_formula_no_deleted_subtraction(self):
        """skipped 计算不应减去 deleted"""
        import inspect

        from rag.vault_indexer import VaultIndexer

        source = inspect.getsource(VaultIndexer.index_vault)
        # 应该是 total_scanned - len(to_index)，不含 len(deleted)
        self.assertIn("total_scanned - len(to_index)", source)
        self.assertNotIn("- len(deleted)", source)


class TestUnifiedDbLock(unittest.TestCase):
    """测试 VecDBClient 统一锁（铁锚终审 MEDIUM-1/2 修复）"""

    def test_no_separate_read_write_locks(self):
        """不应再有 self._read_lock 或 self._write_lock 赋值"""
        import inspect

        from rag.vecdb_client import VecDBClient
        source = inspect.getsource(VecDBClient.__init__)
        self.assertNotIn("self._read_lock", source)
        self.assertNotIn("self._write_lock", source)
        self.assertIn("self._db_lock", source)

    def test_search_by_keyword_uses_db_lock(self):
        """search_by_keyword 应使用 _db_lock"""
        import inspect

        from rag.vecdb_client import VecDBClient

        source = inspect.getsource(VecDBClient.search_by_keyword)
        self.assertIn("_db_lock", source)

    def test_fallback_search_uses_db_lock(self):
        """_fallback_search 应使用 _db_lock"""
        import inspect

        from rag.vecdb_client import VecDBClient

        source = inspect.getsource(VecDBClient._fallback_search)
        self.assertIn("_db_lock", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)