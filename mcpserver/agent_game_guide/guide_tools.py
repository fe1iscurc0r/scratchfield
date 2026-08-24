from __future__ import annotations

from typing import Any

try:
    from guide_engine import GuideRequest
    from guide_engine.models import get_guide_engine_settings
    _GUIDE_ENGINE_AVAILABLE = True
except Exception:
    _GUIDE_ENGINE_AVAILABLE = False
    GuideRequest = None
    get_guide_engine_settings = None


class GuideTools:
    def __init__(self) -> None:
        self._guide_service = None

    @property
    def guide_service(self):
        if not _GUIDE_ENGINE_AVAILABLE:
            return None
        if self._guide_service is None:
            from guide_engine import get_guide_service
            self._guide_service = get_guide_service()
        return self._guide_service

    async def ask_guide(
        self,
        query: str,
        game_id: str | None = None,
        server_id: str | None = None,
        images: list[str] | None = None,
        auto_screenshot: bool | None = None,
        history: list[dict[str, Any]] | None = None,
        force_query_mode: str | None = None,
    ) -> dict[str, Any]:
        if not _GUIDE_ENGINE_AVAILABLE:
            return {"status": "error", "message": "游戏攻略引擎未启用（guide_engine 已禁用）", "data": {}}

        settings = get_guide_engine_settings()
        use_auto_screenshot = settings.auto_screenshot_on_guide if auto_screenshot is None else auto_screenshot

        request = GuideRequest(
            content=query,
            game_id=game_id,
            server_id=server_id,
            images=images or [],
            auto_screenshot=use_auto_screenshot,
            history=history or [],
            force_query_mode=force_query_mode,
        )
        result = await self.guide_service.ask(request)
        return {
            "status": "success",
            "message": "攻略查询成功",
            "data": {
                "response": result.content,
                "query_mode": result.query_mode,
                "references": [item.model_dump() for item in result.references],
                "metadata": result.metadata,
            },
        }

    async def ask_guide_with_screenshot(
        self,
        query: str,
        game_id: str | None = None,
        server_id: str | None = None,
        images: list[str] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return await self.ask_guide(
            query=query,
            game_id=game_id,
            server_id=server_id,
            images=images,
            auto_screenshot=True,
            history=history,
        )

    async def calculate_damage(self, query: str, game_id: str | None = None) -> dict[str, Any]:
        return await self.ask_guide(
            query=query, game_id=game_id, auto_screenshot=False, force_query_mode="calculation",
        )

    async def get_team_recommendation(self, query: str, game_id: str | None = None) -> dict[str, Any]:
        return await self.ask_guide(
            query=query, game_id=game_id, auto_screenshot=True, force_query_mode="full",
        )
