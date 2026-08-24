"""会话管理路由"""

import logging

from fastapi import APIRouter, HTTPException

from apiserver.api_server import _vlm_sessions
from apiserver.message_manager import message_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions")
async def get_sessions():
    """获取所有会话信息 - 委托给message_manager"""
    try:
        return message_manager.get_all_sessions_api()
    except Exception as e:
        logger.error(f"获取会话信息错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/sessions/{session_id}")
async def get_session_detail(session_id: str):
    """获取指定会话的详细信息 - 委托给message_manager"""
    try:
        return message_manager.get_session_detail_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail="会话不存在")
        logger.error(f"获取会话详情错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除指定会话 - 委托给message_manager"""
    try:
        _vlm_sessions.discard(session_id)
        return message_manager.delete_session_api(session_id)
    except Exception as e:
        if "会话不存在" in str(e):
            raise HTTPException(status_code=404, detail="会话不存在")
        logger.error(f"删除会话错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/sessions")
async def clear_all_sessions():
    """清空所有会话 - 委托给message_manager"""
    try:
        _vlm_sessions.clear()
        return message_manager.clear_all_sessions_api()
    except Exception as e:
        logger.error(f"清空会话错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="服务器内部错误")
