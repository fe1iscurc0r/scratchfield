"""
人设 API 路由 - 角色配置与切换接口
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from apiserver.naga_auth import require_local_auth
from system.persona import PersonaConfig, get_persona_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/persona", tags=["人设"])


class CreatePersonaRequest(BaseModel):
    name: str
    ai_name: str = "陆墨"
    personality: str = ""
    system_prompt: str = ""
    style_params: dict[str, Any] | None = None
    bio: str = ""
    voice: str = "zh-CN-XiaoxiaoNeural"


class UpdatePersonaRequest(BaseModel):
    ai_name: str | None = None
    personality: str | None = None
    system_prompt: str | None = None
    style_params: dict[str, Any] | None = None
    bio: str | None = None
    voice: str | None = None


class SetStyleParamRequest(BaseModel):
    key: str
    value: float
    persona_name: str | None = None


@router.get("/list")
async def list_personas(auth: dict = Depends(require_local_auth)):
    """获取所有人设列表"""
    try:
        manager = get_persona_manager()
        return {
            "success": True,
            "personas": manager.list_personas(),
            "active_persona": manager.get_active_persona_name(),
        }
    except Exception as e:
        logger.error(f"获取人设列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/active")
async def get_active_persona(auth: dict = Depends(require_local_auth)):
    """获取当前活跃人设"""
    try:
        manager = get_persona_manager()
        persona = manager.get_persona()
        return {
            "success": True,
            "active_persona": manager.get_active_persona_name(),
            "config": persona.model_dump(),
        }
    except Exception as e:
        logger.error(f"获取活跃人设失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/activate/{persona_name}")
async def activate_persona(persona_name: str, auth: dict = Depends(require_local_auth)):
    """切换人设"""
    try:
        manager = get_persona_manager()
        success = manager.set_active_persona(persona_name)
        if not success:
            raise HTTPException(status_code=404, detail=f"人设 '{persona_name}' 不存在")
        return {"success": True, "active_persona": persona_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换人设失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/create")
async def create_persona(request: CreatePersonaRequest, auth: dict = Depends(require_local_auth)):
    """创建新人设"""
    try:
        manager = get_persona_manager()
        config = PersonaConfig(
            ai_name=request.ai_name,
            personality=request.personality,
            system_prompt=request.system_prompt,
            style_params=request.style_params or {},
            bio=request.bio,
            voice=request.voice,
        )
        success = manager.create_persona(request.name, config)
        if not success:
            raise HTTPException(status_code=400, detail=f"人设 '{request.name}' 已存在")
        return {"success": True, "persona_name": request.name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建人设失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.put("/update/{persona_name}")
async def update_persona(persona_name: str, request: UpdatePersonaRequest, auth: dict = Depends(require_local_auth)):
    """更新人设"""
    try:
        manager = get_persona_manager()
        kwargs = request.model_dump(exclude_unset=True)
        success = manager.update_persona(persona_name, **kwargs)
        if not success:
            raise HTTPException(status_code=404, detail=f"人设 '{persona_name}' 不存在")
        return {"success": True, "persona_name": persona_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新人设失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/delete/{persona_name}")
async def delete_persona(persona_name: str, auth: dict = Depends(require_local_auth)):
    """删除人设"""
    try:
        manager = get_persona_manager()
        success = manager.delete_persona(persona_name)
        if not success:
            raise HTTPException(status_code=400, detail=f"无法删除人设 '{persona_name}'")
        return {"success": True, "deleted_persona": persona_name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除人设失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/style-param")
async def set_style_param(request: SetStyleParamRequest, auth: dict = Depends(require_local_auth)):
    """设置风格参数"""
    try:
        manager = get_persona_manager()
        success = manager.set_style_param(
            key=request.key,
            value=request.value,
            name=request.persona_name,
        )
        if not success:
            raise HTTPException(status_code=400, detail="设置风格参数失败")
        return {
            "success": True,
            "key": request.key,
            "value": request.value,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置风格参数失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/system-prompt")
async def get_system_prompt(persona_name: str | None = None, auth: dict = Depends(require_local_auth)):
    """获取系统提示词"""
    try:
        manager = get_persona_manager()
        prompt = manager.get_system_prompt(persona_name)
        return {
            "success": True,
            "persona": persona_name or manager.get_active_persona_name(),
            "system_prompt": prompt,
        }
    except Exception as e:
        logger.error(f"获取系统提示词失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/style-params")
async def get_style_params(persona_name: str | None = None, auth: dict = Depends(require_local_auth)):
    """获取风格参数"""
    try:
        manager = get_persona_manager()
        params = manager.get_style_params(persona_name)
        return {
            "success": True,
            "persona": persona_name or manager.get_active_persona_name(),
            "style_params": params,
        }
    except Exception as e:
        logger.error(f"获取风格参数失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
