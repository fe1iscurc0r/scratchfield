"""端侧嵌入（卷125 W125-03，参考 OpenSquilla 的 on-device embeddings）。

记忆/检索的 embedding **本地算**，不依赖云端 API：省 token、降延迟、离线可用。
模型沿用仓库自带的 `rag.embedding_engine`（BAAI/bge-small-zh-v1.5），不新引依赖。

选型依据（调研结论，README 同步）：

| 候选 | 体积 | 维度 | 中文 | 许可 | 结论 |
| --- | --- | --- | --- | --- | --- |
| `BAAI/bge-small-zh-v1.5`（**已内置在用**） | ~95MB | 512 | 好（中文检索常用基线） | MIT | **采用**：已在 memclaw/graphrag 跑通，零新增依赖 |
| `text2vec-base-chinese` | ~400MB | 768 | 好 | Apache-2.0 | 备选：体积大 4 倍，收益不明显 |
| `paraphrase-multilingual-MiniLM` | ~470MB | 384 | 一般 | Apache-2.0 | 不选：中文弱于 bge-small-zh |

行为：

- `mode=auto`（默认）：**本地优先**，本地不可用（模型缺失/加载失败）→ 云端 OpenAI 兼容 `/embeddings` 回退
- `mode=local`：只用本地；不可用直接返回 None（调用方决定降级策略）
- `mode=cloud`：只用云端
- LRU 缓存：`sha1(text)` → 向量，命中即省一次计算（默认 512 条）
- 统计：本地/云端调用次数、缓存命中、**节省的 API 调用次数与 token 估算**（README 给公式）
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_DIM_HINT = 512  # bge-small-zh 实际维度（512），加载后以真实维度为准


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "embedder", None)
    except Exception:  # noqa: BLE001
        return None


def mode() -> str:
    cfg = _cfg()
    value = str(getattr(cfg, "mode", "auto") or "auto").strip().lower() if cfg is not None else "auto"
    return value if value in ("auto", "local", "cloud") else "auto"


def cache_size() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "cache_size", 512) or 512) if cfg is not None else 512


# ---------------------------------------------------------------------------
# 本地引擎
# ---------------------------------------------------------------------------


_engine = None
_engine_lock = threading.Lock()
_engine_failed = False


def _local_engine() -> Any:
    """懒加载本地 embedding 引擎（失败只试一次，之后直接走回退）。"""
    global _engine, _engine_failed
    if _engine is not None or _engine_failed:
        return _engine
    with _engine_lock:
        if _engine is not None or _engine_failed:
            return _engine
        try:
            from rag.embedding_engine import get_embedding_engine

            _engine = get_embedding_engine()
            logger.info("[local_embedder] 本地 embedding 引擎就绪（%s）", MODEL_NAME)
        except Exception as e:  # noqa: BLE001 - 不可用则回退云端
            _engine_failed = True
            logger.warning("[local_embedder] 本地引擎不可用，后续走云端回退: %s", e)
    return _engine


def local_available() -> bool:
    engine = _local_engine()
    if engine is None:
        return False
    try:
        import numpy as np  # noqa: F401

        probe = engine.encode(["探活"])
        return probe is not None and len(probe) == 1
    except Exception as e:  # noqa: BLE001
        logger.debug("[local_embedder] 本地引擎探活失败: %s", e)
        return False


def local_dim() -> int:
    engine = _local_engine()
    try:
        return int(engine.get_embedding_dim())
    except Exception:  # noqa: BLE001
        return MODEL_DIM_HINT


# ---------------------------------------------------------------------------
# 云端回退
# ---------------------------------------------------------------------------


def _cloud_config() -> Dict[str, str]:
    """云端 embedding 配置（EmbeddingConfig 优先，其次回退 api.*）。"""
    try:
        cfg = _cfg()
        from system.config import get_config

        api = get_config().api
        base = str(getattr(cfg, "cloud_api_base", "") or "") if cfg is not None else ""
        key = str(getattr(cfg, "cloud_api_key", "") or "") if cfg is not None else ""
        model = str(getattr(cfg, "cloud_model", "") or "") if cfg is not None else ""
        embed_cfg = getattr(get_config(), "embedding", None)
        if embed_cfg is not None:
            base = base or str(getattr(embed_cfg, "api_base", "") or "")
            key = key or str(getattr(embed_cfg, "api_key", "") or "")
            model = model or str(getattr(embed_cfg, "model", "") or "")
        return {
            "api_base": base or str(getattr(api, "base_url", "") or ""),
            "api_key": key or str(getattr(api, "api_key", "") or ""),
            "model": model or "text-embedding-3-small",
        }
    except Exception as e:  # noqa: BLE001
        logger.debug("[local_embedder] 读取云端配置失败: %s", e)
        return {"api_base": "", "api_key": "", "model": ""}


def cloud_available() -> bool:
    conf = _cloud_config()
    return bool(conf["api_base"] and conf["api_key"])


def _cloud_embed(texts: Sequence[str]) -> List[List[float]] | None:
    import httpx

    conf = _cloud_config()
    if not conf["api_base"]:
        return None
    url = conf["api_base"].rstrip("/") + "/embeddings"
    headers = {"Authorization": f"Bearer {conf['api_key']}"} if conf["api_key"] else {}
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json={"model": conf["model"], "input": list(texts)}, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return [list(item["embedding"]) for item in data.get("data", [])]
    except Exception as e:  # noqa: BLE001 - 云端失败返回 None（调用方处理）
        logger.warning("[local_embedder] 云端 embedding 失败: %s", e)
        return None


# ---------------------------------------------------------------------------
# LRU 缓存
# ---------------------------------------------------------------------------


class _VectorCache:
    def __init__(self, capacity: int | None = None) -> None:
        # capacity=None → 每次写入时按配置读（改 config 不必重建缓存）
        self._fixed_capacity = int(capacity) if capacity is not None else None
        self._data: "OrderedDict[str, List[float]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def capacity(self) -> int:
        return max(1, self._fixed_capacity if self._fixed_capacity is not None else cache_size())

    @staticmethod
    def key(text: str) -> str:
        # 仅作缓存键（非安全用途）；用 sha256 避免弱算法扫描告警
        return hashlib.sha256(str(text).encode("utf-8")).hexdigest()

    def get(self, text: str) -> List[float] | None:
        k = self.key(text)
        with self._lock:
            if k in self._data:
                self._data.move_to_end(k)
                self.hits += 1
                return self._data[k]
            self.misses += 1
            return None

    def put(self, text: str, vector: List[float]) -> None:
        k = self.key(text)
        with self._lock:
            self._data[k] = list(vector)
            self._data.move_to_end(k)
            while len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


_cache = _VectorCache()  # capacity=None → 跟随 config.embedder.cache_size
_stats: Dict[str, Any] = {"local_calls": 0, "cloud_calls": 0, "fallbacks": 0, "texts_embedded": 0,
                          "local_batches": 0, "cloud_batches": 0}
_stats_lock = threading.Lock()


def _bump(key: str, amount: int = 1) -> None:
    with _stats_lock:
        _stats[key] = int(_stats.get(key, 0)) + amount


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------


def embed(texts: Sequence[str], *, use_cache: bool = True,
          mode_override: str | None = None) -> List[List[float]] | None:
    """把文本编码成向量。

    Returns:
        向量列表（与入参等长）；本地与云端都不可用返回 None（调用方决定降级）。
    """
    items = [str(t) for t in (texts or [])]
    if not items:
        return []
    selected = (mode_override or mode()).lower()

    vectors: List[List[float] | None] = [None] * len(items)
    pending: List[int] = []
    for idx, text in enumerate(items):
        cached = _cache.get(text) if use_cache else None
        if cached is not None:
            vectors[idx] = cached
        else:
            pending.append(idx)

    if pending:
        todo = [items[i] for i in pending]
        produced: List[List[float]] | None = None

        if selected in ("auto", "local"):
            engine = _local_engine()
            if engine is not None:
                try:
                    raw = engine.encode(todo)
                    if raw is not None:
                        produced = [list(map(float, row)) for row in raw]
                        _bump("local_calls", len(todo))
                        _bump("local_batches")
                except Exception as e:  # noqa: BLE001 - 本地失败 → 走回退
                    logger.warning("[local_embedder] 本地编码失败，尝试回退: %s", e)
                    produced = None
            if produced is None and selected == "local":
                logger.warning("[local_embedder] mode=local 且本地不可用，返回 None")
                return None

        if produced is None and selected in ("auto", "cloud"):
            if selected == "auto":
                _bump("fallbacks")
            produced = _cloud_embed(todo)
            if produced is not None:
                _bump("cloud_calls", len(todo))
                _bump("cloud_batches")
        if produced is None:
            logger.error("[local_embedder] 本地与云端均不可用，embedding 失败")
            return None

        for offset, idx in enumerate(pending):
            vector = produced[offset] if offset < len(produced) else []
            vectors[idx] = vector
            if use_cache and vector:
                _cache.put(items[idx], vector)
        _bump("texts_embedded", len(todo))

    return [v if v is not None else [] for v in vectors]


def embed_one(text: str, **kwargs: Any) -> List[float] | None:
    out = embed([text], **kwargs)
    return out[0] if out else None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度（本地向量已归一化，点积即余弦；这里仍做通用实现）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = sum(float(x) * float(x) for x in a) ** 0.5
    nb = sum(float(y) * float(y) for y in b) ** 0.5
    return float(dot / (na * nb)) if na and nb else 0.0


def estimate_saved_tokens(texts: Sequence[str], *, cloud_price_per_1k: float = 0.0,
                          chars_per_token: float = 4.0) -> Dict[str, Any]:
    """本地嵌入相对云端 API 的节省估算。

    口径：token ≈ 字符数 / `chars_per_token`（默认 4，中文约 1.5 字/token，可按需调）；
    金额 = tokens / 1000 × `cloud_price_per_1k`（价格从配置或入参给，README 写公式）。
    """
    chars = sum(len(str(t)) for t in (texts or []))
    tokens = chars / max(0.5, float(chars_per_token))
    return {
        "texts": len(list(texts or [])),
        "chars": chars,
        "tokens_estimate": round(tokens, 1),
        "cloud_cost_estimate": round(tokens / 1000.0 * float(cloud_price_per_1k), 6),
        "formula": "tokens ≈ chars / chars_per_token；cost = tokens/1000 × price_per_1k",
    }


def stats() -> Dict[str, Any]:
    with _stats_lock:
        snapshot = dict(_stats)
    snapshot.update({
        "mode": mode(),
        "model": MODEL_NAME,
        "dim": local_dim(),
        "local_available": local_available(),
        "cloud_available": cloud_available(),
        "cache": {"size": len(_cache), "capacity": _cache.capacity,
                  "hits": _cache.hits, "misses": _cache.misses},
    })
    return snapshot


def reset_for_tests(capacity: int | None = None) -> None:
    """测试用：清缓存与统计（不卸模型，避免反复加载）。

    `capacity=None` 时保持「跟随配置」语义（不是把当前配置值固化成固定容量）。
    """
    global _cache, _engine_failed
    _cache = _VectorCache(capacity)
    with _stats_lock:
        for key in _stats:
            _stats[key] = 0
    _engine_failed = False
