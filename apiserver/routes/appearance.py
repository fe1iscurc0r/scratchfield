"""
外观定制 API 路由 - 主题与样式接口
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apiserver.naga_auth import require_local_auth
from system.appearance import get_appearance_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/appearance", tags=["外观"])


class SetThemeRequest(BaseModel):
    theme_name: str


class SetColorsRequest(BaseModel):
    primary: str | None = None
    secondary: str | None = None
    accent: str | None = None
    background: str | None = None
    surface: str | None = None
    text_primary: str | None = None
    text_secondary: str | None = None
    border: str | None = None


class SetDialogStyleRequest(BaseModel):
    border_radius: str | None = None
    border_width: int | None = None
    shadow: str | None = None
    padding: str | None = None
    max_width: str | None = None


class SetFontRequest(BaseModel):
    font_family: str | None = None
    font_size_base: str | None = None


class SetAvatarRequest(BaseModel):
    avatar_path: str


@router.get("/config")
async def get_appearance_config(auth: dict = Depends(require_local_auth)):
    """获取当前外观配置"""
    try:
        manager = get_appearance_manager()
        return {
            "success": True,
            "config": manager.get_frontend_config(),
        }
    except Exception as e:
        logger.error(f"获取外观配置失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/themes")
async def list_themes(auth: dict = Depends(require_local_auth)):
    """获取所有可用主题"""
    try:
        manager = get_appearance_manager()
        return {
            "success": True,
            "themes": manager.list_themes(),
            "active_theme": manager.get_config().theme_name,
        }
    except Exception as e:
        logger.error(f"获取主题列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/theme")
async def set_theme(request: SetThemeRequest, auth: dict = Depends(require_local_auth)):
    """切换主题"""
    try:
        manager = get_appearance_manager()
        success = manager.set_theme(request.theme_name)
        if not success:
            raise HTTPException(status_code=404, detail=f"主题 '{request.theme_name}' 不存在")
        return {
            "success": True,
            "theme_name": request.theme_name,
            "config": manager.get_frontend_config(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换主题失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/colors")
async def set_colors(request: SetColorsRequest, auth: dict = Depends(require_local_auth)):
    """自定义配色"""
    try:
        manager = get_appearance_manager()
        kwargs = request.model_dump(exclude_unset=True)
        success = manager.set_colors(**kwargs)
        if not success:
            raise HTTPException(status_code=400, detail="设置配色失败")
        return {
            "success": True,
            "colors": manager.get_config().colors.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置配色失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/dialog-style")
async def set_dialog_style(request: SetDialogStyleRequest, auth: dict = Depends(require_local_auth)):
    """设置对话框样式"""
    try:
        manager = get_appearance_manager()
        kwargs = request.model_dump(exclude_unset=True)
        success = manager.set_dialog_style(**kwargs)
        if not success:
            raise HTTPException(status_code=400, detail="设置对话框样式失败")
        return {
            "success": True,
            "dialog_style": manager.get_config().dialog_style.model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置对话框样式失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/avatar")
async def set_avatar(request: SetAvatarRequest, auth: dict = Depends(require_local_auth)):
    """设置头像"""
    try:
        manager = get_appearance_manager()
        success = manager.set_avatar(request.avatar_path)
        return {"success": success, "avatar": request.avatar_path}
    except Exception as e:
        logger.error(f"设置头像失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/font")
async def set_font(request: SetFontRequest, auth: dict = Depends(require_local_auth)):
    """设置字体"""
    try:
        manager = get_appearance_manager()
        success = manager.set_font(
            font_family=request.font_family,
            font_size=request.font_size_base,
        )
        return {"success": success}
    except Exception as e:
        logger.error(f"设置字体失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/density/{density}")
async def set_density(density: str, auth: dict = Depends(require_local_auth)):
    """设置密度"""
    try:
        manager = get_appearance_manager()
        success = manager.set_density(density)
        if not success:
            raise HTTPException(status_code=400, detail="密度值无效，支持: compact, normal, comfortable")
        return {"success": True, "density": density}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置密度失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/css-variables")
async def get_css_variables(auth: dict = Depends(require_local_auth)):
    """获取 CSS 变量"""
    try:
        manager = get_appearance_manager()
        css = manager.generate_css_variables()
        return {"success": True, "css": css}
    except Exception as e:
        logger.error(f"获取 CSS 变量失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
