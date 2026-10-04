"""
Vault 索引器 - 对 Markdown 仓库（如 Obsidian vault）做增量索引。

设计要点（铁锚审查修复点）：
- 增量索引：基于内容哈希的状态文件（.vault_index_state.json），
  只处理新增/变更文件，删除磁盘上已消失文件的旧数据。
- 原子写入：状态文件先写临时文件再 os.replace，异常时清理临时文件，
  不残留 .tmp 中间文件。
- 线程安全：模块级 _indexer_lock 双重检查锁单例；实例内 _state_lock
  保护 _indexed_hashes 状态读写。
- 与 RAG 知识库联动：入库 metadata 带 source="vault" 与 rel_path，
  清理旧数据时按 metadata 键值对删除。
"""
import hashlib
import json
import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 状态文件名（vault 根目录下）
_STATE_FILE_NAME = ".vault_index_state.json"

# 模块级锁：get_vault_indexer 双重检查锁用
_indexer_lock = threading.Lock()

# 全局单例（惰性创建）
_vault_indexer_instance: Optional["VaultIndexer"] = None


def _default_vault_dir() -> Path:
    """默认 vault 目录：用户数据目录下 vault（不存在则创建）。"""
    from system.config import get_data_dir

    d = get_data_dir() / "vault"
    d.mkdir(parents=True, exist_ok=True)
    return d


class VaultIndexer:
    """Markdown vault 增量索引器。

    - scan_files(): 扫描 *.md，跳过隐藏目录/文件，返回 (file_path, source, rel_path)
    - _compute_hash(): 文件内容哈希（md5 前 8 字节 → 16 位十六进制）
    - get_changed_files(): 对比状态文件，返回 (to_index, deleted, total)
    - index_vault(): 增量/全量索引到 RAG 知识库（force 先清空 source=vault 旧数据）
    - _save_state(): 原子写状态文件（临时文件 + os.replace）
    - get_indexed_count(): 线程安全返回已索引文件数
    """

    def __init__(self, vault_dir: str | Path | None = None):
        if vault_dir is None:
            vault_dir = _default_vault_dir()
        self.vault_dir = Path(vault_dir)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.source = "vault"
        self._state_lock = threading.Lock()
        self._indexed_hashes: Dict[str, str] = {}
        self._state_file = self.vault_dir / _STATE_FILE_NAME
        self._load_state()

    # ------------------------------------------------------------------
    # 扫描
    # ------------------------------------------------------------------

    def scan_files(self) -> List[Tuple[Path, str, str]]:
        """扫描 vault 下所有 *.md 文件（跳过隐藏目录/文件）。

        Returns:
            [(file_path, source, rel_path), ...]；rel_path 为相对 vault 根的 posix 路径。
        """
        results: List[Tuple[Path, str, str]] = []
        for root, dirs, files in os.walk(self.vault_dir):
            # 跳过隐藏目录（如 .obsidian / .trash）
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                # 跳过隐藏文件与非 markdown
                if name.startswith("."):
                    continue
                if not name.lower().endswith(".md"):
                    continue
                fp = Path(root) / name
                rel = fp.relative_to(self.vault_dir).as_posix()
                results.append((fp, self.source, rel))
        # 稳定顺序，便于增量比对与测试断言
        results.sort(key=lambda x: x[2])
        return results

    # ------------------------------------------------------------------
    # 哈希
    # ------------------------------------------------------------------

    def _compute_hash(self, file_path: Path) -> str:
        """计算文件内容哈希：md5 前 8 字节 → 16 位十六进制字符串。"""
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()[:16]

    # ------------------------------------------------------------------
    # 状态读写
    # ------------------------------------------------------------------

    def _load_state(self):
        """从状态文件加载已索引哈希（损坏时重置，不影响使用）。"""
        with self._state_lock:
            if not self._state_file.exists():
                self._indexed_hashes = {}
                return
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._indexed_hashes = {str(k): str(v) for k, v in data.items()}
                else:
                    self._indexed_hashes = {}
            except Exception as e:
                logger.warning(f"[Vault] 状态文件读取失败，重置索引状态: {e}")
                self._indexed_hashes = {}

    def _save_state(self):
        """原子写入状态文件：临时文件 + os.replace，不残留 .tmp 中间文件。

        临时文件用 tempfile.mkstemp 生成（无 .tmp 后缀），
        写入成功后 os.replace 原子替换；失败时清理临时文件并重抛。
        """
        with self._state_lock:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self.vault_dir), prefix=".vault_state_"
            )
            try:
                with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                    json.dump(self._indexed_hashes, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self._state_file)
            except Exception:
                # 清理临时文件，避免残留
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

    def get_indexed_count(self) -> int:
        """已索引文件数（线程安全）。"""
        with self._state_lock:
            return len(self._indexed_hashes)

    # ------------------------------------------------------------------
    # 增量比对
    # ------------------------------------------------------------------

    def get_changed_files(self) -> Tuple[List[Tuple[Path, str, str, str]], List[str], int]:
        """对比扫描结果与状态文件，找出需要处理的文件。

        Returns:
            to_index: [(file_path, source, state_key, hash_val), ...]
                      state_key 形如 "vault:rel_path"
            deleted:  磁盘上已消失文件的 state_key 列表
            total:    本次扫描到的文件总数
        """
        with self._state_lock:
            files = self.scan_files()
            total = len(files)
            current_keys = set()
            to_index: List[Tuple[Path, str, str, str]] = []
            for fp, source, rel in files:
                state_key = f"{source}:{rel}"
                current_keys.add(state_key)
                hash_val = self._compute_hash(fp)
                if self._indexed_hashes.get(state_key) != hash_val:
                    to_index.append((fp, source, state_key, hash_val))
            deleted = [k for k in self._indexed_hashes if k not in current_keys]
            return to_index, deleted, total

    # ------------------------------------------------------------------
    # 索引入口
    # ------------------------------------------------------------------

    def index_vault(self, force: bool = False) -> dict[str, Any]:
        """增量/全量索引 vault 到 RAG 知识库。

        Args:
            force: True 时先按 source=vault 清空旧数据，再全量重建；
                   False 时只索引新增/变更文件，并删除已消失文件的旧数据。

        Returns:
            {success, total, indexed, skipped, deleted, errors}
        """
        from rag import get_rag_service

        rag_service = get_rag_service()
        to_index, deleted, total = self.get_changed_files()
        total_scanned = total

        if force:
            # 全量重建：先按 source=vault 删除全部旧文档
            rag_service.delete_by_metadata({"source": "vault"})
            with self._state_lock:
                self._indexed_hashes = {}
            # 清空状态后重新比对，得到全量 to_index
            to_index, deleted, total = self.get_changed_files()
            total_scanned = total

        # 清理磁盘上已删除文件的旧数据（按 rel_path 精确删除）
        for state_key in deleted:
            rel_path = state_key.split(":", 1)[1] if ":" in state_key else state_key
            try:
                rag_service.delete_by_metadata({"source": "vault", "rel_path": rel_path})
            except Exception as e:
                logger.warning(f"[Vault] 清理旧数据失败: {rel_path}: {e}")
            with self._state_lock:
                self._indexed_hashes.pop(state_key, None)

        # 增量入库
        indexed = 0
        errors = 0
        for fp, source, state_key, hash_val in to_index:
            rel_path = state_key.split(":", 1)[1] if ":" in state_key else state_key
            try:
                result = rag_service.ingest_document(
                    file_path=str(fp),
                    title=fp.stem,
                    tags=[],
                    metadata={"source": "vault", "rel_path": rel_path},
                )
                if result.get("success"):
                    with self._state_lock:
                        self._indexed_hashes[state_key] = hash_val
                    indexed += 1
                else:
                    errors += 1
                    logger.warning(f"[Vault] 索引失败: {rel_path}: {result.get('error')}")
            except Exception as e:
                errors += 1
                logger.warning(f"[Vault] 索引异常: {rel_path}: {e}")

        self._save_state()

        # skipped = 本次扫描总数 - 待索引数（内容未变化的文件）
        skipped = total_scanned - len(to_index)
        return {
            "success": True,
            "total": total_scanned,
            "indexed": indexed,
            "skipped": skipped,
            "deleted": len(deleted),
            "errors": errors,
        }


def get_vault_indexer() -> VaultIndexer:
    """获取全局 VaultIndexer 单例（双重检查锁，线程安全）。"""
    global _vault_indexer_instance
    if _vault_indexer_instance is None:
        with _indexer_lock:
            if _vault_indexer_instance is None:
                _vault_indexer_instance = VaultIndexer()
    return _vault_indexer_instance
