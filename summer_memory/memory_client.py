"""
NagaMemory 远程记忆微服务客户端

轻量级 HTTP 客户端，将本地 summer_memory 的图谱/五元组操作
代理到远程 NagaMemory 服务（NebulaGraph 后端）。

已登录时自动启用（优先使用 naga_auth 动态 token），未登录时返回 None。

用法::

    from summer_memory.memory_client import get_remote_memory_client

    client = get_remote_memory_client()
    if client is None:
        # 未登录，走本地 summer_memory 逻辑
        ...
    else:
        stats = await client.get_stats()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("NagaMemoryClient")

QuintupleType = tuple[str, str, str, str, str]


class RemoteMemoryClient:
    """异步 NagaMemory 远程客户端"""

    def __init__(self, base_url: str, token: str | None = None, space_id: str | None = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if space_id:
            headers["X-Space-Id"] = space_id
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def close(self):
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            resp = await self._client.request(method, url, **kwargs)

            # 401 自动刷新 token 并重试一次
            if resp.status_code == 401:
                logger.warning(f"NagaMemory 返回 401 [{method} {path}]，尝试刷新 token...")
                try:
                    from apiserver.naga_auth import get_access_token
                    from apiserver.naga_auth import refresh as naga_refresh
                    await naga_refresh()
                    new_token = get_access_token()
                    if new_token:
                        self._client.headers["Authorization"] = f"Bearer {new_token}"
                        # 重置全局单例，使下次 get_remote_memory_client() 用新 token 重建
                        global _client
                        _client = None
                        logger.info("token 刷新成功，正在重试请求...")
                        resp = await self._client.request(method, url, **kwargs)
                    else:
                        logger.error("token 刷新后仍无 access_token")
                except Exception as refresh_err:
                    logger.error(f"token 刷新失败: {refresh_err}")

            resp.raise_for_status()
            if not resp.content:
                logger.warning(f"NagaMemory 返回空响应 [{method} {path}] status={resp.status_code}")
                return {"success": False, "error": "服务返回空响应，请检查网络或代理设置"}
            content_type = resp.headers.get("content-type", "")
            text_preview = resp.text[:300].replace("\n", "\\n")
            if "json" not in content_type.lower():
                logger.warning(
                    "NagaMemory 响应 Content-Type 非 JSON [%s %s]: %s preview=%r",
                    method,
                    path,
                    content_type or "<missing>",
                    text_preview,
                )
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"NagaMemory HTTP {e.response.status_code} [{method} {path}]: {e}")
            # 401/403 认证失败 → 抛出异常，让上层回退到本地记忆
            if e.response.status_code in (401, 403):
                raise
            return {"success": False, "error": str(e)}
        except httpx.HTTPError as e:
            logger.error(f"NagaMemory 请求失败 [{method} {path}]: {e}")
            return {"success": False, "error": str(e)}
        except ValueError as e:
            snippet = ""
            try:
                snippet = resp.text[:300].replace("\n", "\\n")
            except Exception:
                pass
            logger.error(f"NagaMemory 响应解析失败 [{method} {path}]: {e}; body={snippet!r}")
            return {"success": False, "error": f"服务返回非JSON响应: {e}"}

    # ---- 健康 / 统计 ----

    async def health_check(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def get_stats(self) -> dict[str, Any]:
        return await self._request("GET", "/stats")

    # ---- 五元组 ----

    async def add_quintuples(self, quintuples: list[QuintupleType]) -> dict[str, Any]:
        return await self._request("POST", "/quintuples", json={"quintuples": quintuples})

    async def get_quintuples(self, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._request("GET", f"/quintuples?limit={limit}&offset={offset}")

    async def query_by_keywords(self, keywords: list[str], limit: int = 10) -> dict[str, Any]:
        return await self._request("POST", "/quintuples/query", json={"keywords": keywords, "limit": limit})

    async def query_by_entity(self, entity_name: str, direction: str = "both", limit: int = 20) -> dict[str, Any]:
        return await self._request("GET", f"/quintuples/entity/{entity_name}?direction={direction}&limit={limit}")

    # ---- 记忆（对话级） ----

    async def add_memory(self, user_input: str = "", ai_response: str = "",
                         quintuples: list[QuintupleType] | None = None) -> dict[str, Any]:
        data: dict[str, Any] = {"user_input": user_input, "ai_response": ai_response}
        if quintuples:
            data["quintuples"] = quintuples
        return await self._request("POST", "/add", json=data)

    async def query_memory(self, question: str = "", keywords: list[str] | None = None,
                           limit: int = 5) -> dict[str, Any]:
        data: dict[str, Any] = {"question": question, "limit": limit}
        if keywords:
            data["keywords"] = keywords
        return await self._request("POST", "/query", json=data)

    # ---- 图查询 ----

    async def get_entities(self, entity_type: str | None = None, limit: int = 100) -> dict[str, Any]:
        params = f"?limit={limit}"
        if entity_type:
            params += f"&type={entity_type}"
        return await self._request("GET", f"/graph/entities{params}")

    async def get_relationships(self) -> dict[str, Any]:
        return await self._request("GET", "/graph/relationships")


# ---- 全局单例 ----

_client: RemoteMemoryClient | None = None
_client_token: str | None = None


def should_prefer_remote_memory() -> bool:
    """
    是否应优先走远程记忆链路。

    前提：必须存在真实可用的远程记忆端点（NAGA_MEMORY_URL 已配置）。
    本地模式下后端自身签发的 refresh_token 不代表云端会话，
    不能据此切远程链路——否则纯本地部署会被误报“云端记忆服务暂不可用”。
    显式配置了 memory_server.token 时仍视为远程优先。
    """
    try:
        from apiserver import naga_auth

        if naga_auth.NAGA_MEMORY_URL:
            if naga_auth.is_authenticated() or naga_auth.has_refresh_token():
                return True
    except Exception:
        pass

    try:
        from system.config import config

        return bool(config.memory_server.token)
    except Exception:
        return False


def get_remote_memory_client() -> RemoteMemoryClient | None:
    """
    获取远程记忆客户端单例。

    优先使用 naga_auth 的动态 access_token（登录/刷新后自动更新），
    回退到 config.memory_server.token。无可用 token 时返回 None
    （调用方应回退到本地 summer_memory）。
    每次调用会重新检查 token，支持热更新和 token 刷新。
    """
    global _client, _client_token

    # 优先使用 naga_auth 动态 token（延迟 import 避免循环引用）
    token: str | None = None
    try:
        from apiserver.naga_auth import get_access_token
        token = get_access_token()
    except Exception:
        pass

    # 回退到 config 静态 token
    if not token:
        try:
            from system.config import config
            token = config.memory_server.token
        except Exception:
            pass

    if not token:
        # 无可用 token，清理已有客户端
        if _client is not None:
            logger.info("NagaMemory 远程客户端已释放（无可用 token）")
            _client = None
            _client_token = None
        return None

    # 获取服务地址和空间ID
    try:
        from system.config import config
        base_url = config.memory_server.url
        space_id = getattr(config.memory_server, 'space_id', None)
    except Exception:
        base_url = "http://localhost:8004"
        space_id = None

    # Token 变更时重新创建客户端
    if _client is not None and token != _client_token:
        logger.info("NagaMemory token 已变更，重新创建客户端")
        _client = None

    if _client is not None:
        return _client

    try:
        _client = RemoteMemoryClient(base_url=base_url, token=token, space_id=space_id)
        _client_token = token
        logger.info(f"NagaMemory 远程客户端已创建: {base_url}" + (f" (space_id={space_id})" if space_id else ""))
        return _client
    except Exception as e:
        logger.warning(f"创建 NagaMemory 客户端失败: {e}")
        return None
