# [local-patch] 陆墨融合注入端点（M3 双向事件）
# 本文件由陆墨融合项目新增，不属于 NEKO 上游源码。
# 详见 .upstream-sha 的 local-patch 记录。
"""
陆墨注入端点 — scratchpad → NEKO 的 REST 推送通道

职责：
  1) POST /api/lumo/speak — 注入说话指令（陆墨决策 → NEKO 执行 TTS + 字幕）
  2) POST /api/lumo/emotion — 注入表情切换（陆墨决策 → NEKO 切换 Live2D 表情）

鉴权：
  - 使用 LUMO_PROXY_TOKEN 环境变量（铁律7）
  - hmac.compare_digest 防时序攻击

数据流：
  scratchpad 判断时机 → POST /api/lumo/speak 或 /api/lumo/emotion
  → 本端点校验 token → 写入 sync_message_queue
  → NEKO 前端 WebSocket 收到消息 → 执行 TTS / 表情切换
"""
import os
import hmac
import asyncio
import logging
import httpx
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/lumo", tags=["lumo-inject"])
logger = logging.getLogger(__name__)

_HTTP_CLIENT: httpx.AsyncClient | None = None

def _get_http_client() -> httpx.AsyncClient:
    """获取或创建模块级 httpx.AsyncClient 实例，复用连接池。"""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient()
    return _HTTP_CLIENT

# ============ 铁律7：fail-fast 凭证 ============
# H1 修复：改为函数级延迟读取，兼容 ConfigManager 注入和环境变量两种配置源

def _resolve_lumo_proxy_token() -> str:
    """延迟读取 LUMO_PROXY_TOKEN，优先环境变量，兜底 ConfigManager。"""
    token = os.environ.get("LUMO_PROXY_TOKEN", "").strip()
    if token:
        return token
    # 兜底：ConfigManager 可能在运行时注入
    try:
        from utils.config_manager.core_config import ConfigManager
        cm = ConfigManager()
        return str(cm.get_config("assistApiKeyLumo", "") or "").strip()
    except Exception:
        return ""


async def require_proxy_token(request: Request) -> dict:
    """跨进程鉴权依赖（scratchpad → NEKO）。

    与 NEKO 本地鉴权独立，强制校验共享密钥，无放行分支。
    用 hmac.compare_digest 防时序攻击。
    H1 修复：每次请求延迟读取 token，兼容前端配置 + 环境变量。
    """
    _token = _resolve_lumo_proxy_token()
    if not _token:
        # 铁锚 LOW-9：不泄露内部配置状态，用通用消息
        raise HTTPException(status_code=503, detail="service unavailable")

    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        raise HTTPException(status_code=401, detail="missing credentials")

    # Python 3 str 版 compare_digest 为 constant-time，直接比较避免
    # .encode("utf-8") 在非 UTF-8 token 下抛 UnicodeEncodeError 暴露异常分支
    if not hmac.compare_digest(token, _token):
        raise HTTPException(status_code=401, detail="invalid credentials")

    # 返回值不含 token（沈遥 R4：防日志/异常链泄露密钥）
    return {"auth": "proxy"}


# ============ 请求模型 ============


class SpeakRequest(BaseModel):
    # 沈遥 R3：长度上限防 OOM；铁锚 MEDIUM-6：min_length 防 empty payload
    lanlan_name: str = Field(..., min_length=1, max_length=64, description="目标角色名")
    text: str = Field(..., min_length=1, max_length=4096, description="注入的说话内容")
    emotion: Optional[str] = Field(None, max_length=32, description="伴随表情（可选）")
    emotion_confidence: float = Field(0.5, ge=0.0, le=1.0, description="表情置信度（与 EmotionRequest 对齐）")


class EmotionRequest(BaseModel):
    lanlan_name: str = Field(..., min_length=1, max_length=64, description="目标角色名")
    emotion: str = Field(..., min_length=1, max_length=32, description="neutral/happy/sad/angry/surprised")
    # 铁锚 LOW-7：与 SpeakRequest.emotion_confidence 默认值统一（0.5），
    # 避免同一 emotion 标签经不同端点产生不同规范化结果
    # 沈遥 No.6：默认 0.5 不触发宽松 fuzzy 分支（<0.72），更严格匹配
    confidence: float = Field(0.5, ge=0.0, le=1.0)


# ============ 端点定义 ============


@router.post("/speak")
async def inject_speak(req: SpeakRequest, _auth: dict = Depends(require_proxy_token)):
    """注入说话指令 → NEKO 前端显示字幕 + TTS 合成。

    复用 sync_message_queue 推送，data.type="speak"。
    前端 WebSocket 收到后处理显示和语音合成。

    注意：speak 是陆墨扩展消息类型，NEKO 前端需在 M3 阶段适配
    app-websocket.js 的 onmessage 分支。当前 M1 阶段端点存在且鉴权可用即可。
    emotion 字段若提供，会先于 speak 触发表情切换。
    """
    from .shared_state import get_sync_message_queue
    from .system_router.emotion import _normalize_emotion_label

    queue = get_sync_message_queue()
    # 铁锚 HIGH-2：__contains__ 与 __getitem__ 间存在 TOCTOU，改用 try/except
    try:
        q = queue[req.lanlan_name]
    except KeyError:
        raise HTTPException(status_code=404, detail="target not found")

    # 审计日志（沈遥 R4：不记 text 全文，只记长度；铁锚 #7：不记原始 emotion 输入值）
    # 沈遥 No.7：额外记 emotion_confidence，便于排查 fuzzy 匹配分支
    logger.info(f"[lumo_inject] action=speak char={req.lanlan_name} text_len={len(req.text)} emotion={'present' if req.emotion else 'none'} emotion_confidence={req.emotion_confidence}")

    # issue #17：队列余量预检——本次请求需要入队的消息数（带 emotion 为 2 条），
    # 余量不足时在任何消息入队前直接 429，根治"emotion 已入队但 speak 429"
    # 导致前端切了表情却没声音/字幕的部分成功。极端 race 下仍有下方
    # QueueFull 兜底（预检与 put 之间可能被别的请求填满），但窗口已收至极小。
    needed_slots = 2 if req.emotion else 1
    if q.maxsize > 0 and q.qsize() + needed_slots > q.maxsize:
        logger.warning("[lumo_inject] queue headroom insufficient (need=%d size=%d/%d), reject before enqueue char=%s",
                       needed_slots, q.qsize(), q.maxsize, req.lanlan_name)
        raise HTTPException(status_code=429, detail="queue saturated", headers={"Retry-After": "1"})

    # 若附带 emotion，先推 emotion（铁锚 #1：规范化标签）
    if req.emotion:
        normalized_emotion = _normalize_emotion_label(req.emotion, req.emotion_confidence)
        emotion_payload = {
            "type": "emotion",
            "emotion": normalized_emotion,
            "confidence": req.emotion_confidence,
        }
        try:
            q.put({"type": "json", "data": emotion_payload})
        except asyncio.QueueFull:
            logger.warning("[lumo_inject] queue full, emotion dropped char=%s", req.lanlan_name)
            raise HTTPException(status_code=429, detail="queue saturated", headers={"Retry-After": "1"})
        # P1-3 修复：同时直发前端 WebSocket（与 inject_emotion 端点一致）
        # 铁锚复审 MEDIUM-1：加 websocket_lock 串行化
        try:
            from .shared_state import get_session_manager
            mgr = get_session_manager().get(req.lanlan_name)
            if mgr and mgr.websocket and hasattr(mgr.websocket, 'client_state') \
                    and mgr.websocket.client_state == mgr.websocket.client_state.CONNECTED:
                ws_lock = getattr(mgr, 'websocket_lock', None)
                if ws_lock:
                    async with ws_lock:
                        await mgr.websocket.send_json(emotion_payload)
                else:
                    await mgr.websocket.send_json(emotion_payload)
        except Exception as e:
            logger.warning("[lumo_inject] speak emotion websocket direct-send failed char=%s: %s", req.lanlan_name, e)

    # 推 speak 指令（陆墨扩展类型，前端需适配）
    # 铁锚 MEDIUM：捕获 QueueFull，避免极端 race 下返回 500
    # 沈遥 R3：用 429 而非 503——队列满是背压，非服务故障，避免客户端按 503 重试打满队列
    # issue #17：部分成功语义已由上方余量预检根治；此处 QueueFull 仅作为
    #   预检后极端 race 的兜底，不再是常规路径
    try:
        q.put({
            "type": "json",
            "data": {
                "type": "speak",
                "text": req.text,
            }
        })
    except asyncio.QueueFull:
        logger.warning("[lumo_inject] queue full, speak dropped char=%s", req.lanlan_name)
        raise HTTPException(status_code=429, detail="queue saturated", headers={"Retry-After": "1"})
    return {"success": True, "queued": True, "character": req.lanlan_name}


@router.post("/emotion")
async def inject_emotion(req: EmotionRequest, _auth: dict = Depends(require_proxy_token)):
    """注入表情切换 → NEKO Live2D 表情参数变更。

    复用 emotion.py:_push_emotion_update 的推送格式 + _normalize_emotion_label 规范化，
    保证 NEKO 前端处理路径零差异。

    P1-3 修复：emotion 消息除入 sync_message_queue（给 monitor_server）外，
    同时通过 session_manager.websocket 直发前端，与 turn.py 双发模式对齐。
    原因：cross_server 的 sync_slot 连接 monitor_server，不连前端 WebSocket，
    导致前端 emotion 分支是死代码。
    """
    from .shared_state import get_sync_message_queue, get_session_manager
    from .system_router.emotion import _normalize_emotion_label

    queue = get_sync_message_queue()
    # 铁锚 HIGH-2：__contains__ 与 __getitem__ 间存在 TOCTOU，改用 try/except
    try:
        q = queue[req.lanlan_name]
    except KeyError:
        raise HTTPException(status_code=404, detail="target not found")

    # 铁锚 #1：规范化 emotion 标签（与原生 emotion.py 路径一致）
    normalized_emotion = _normalize_emotion_label(req.emotion, req.confidence)

    # 审计日志（铁锚 #7：不记原始 emotion 输入值，只记规范化结果）
    logger.info(f"[lumo_inject] action=emotion char={req.lanlan_name} emotion_normalized={normalized_emotion}")

    # emotion 消息载荷（前端 response.type === 'emotion' 分支匹配）
    emotion_payload = {
        "type": "emotion",
        "emotion": normalized_emotion,
        "confidence": req.confidence
    }

    # 1. 入 sync_message_queue → cross_server → monitor_server（原有路径）
    # 铁锚 MEDIUM：捕获 QueueFull，避免极端 race 下返回 500
    # 沈遥 R3：用 429 而非 503——队列满是背压，非服务故障
    try:
        q.put({"type": "json", "data": emotion_payload})
    except asyncio.QueueFull:
        logger.warning("[lumo_inject] queue full, emotion dropped char=%s", req.lanlan_name)
        raise HTTPException(status_code=429, detail="queue saturated", headers={"Retry-After": "1"})

    # 2. P1-3 修复：直发前端 WebSocket（与 turn.py:315-318 双发模式对齐）
    #    sync_slot 只连 monitor_server，前端收不到 emotion 消息
    #    铁锚复审 MEDIUM-1：加 websocket_lock 串行化，防并发帧损坏
    try:
        mgr = get_session_manager().get(req.lanlan_name)
        if mgr and mgr.websocket and hasattr(mgr.websocket, 'client_state') \
                and mgr.websocket.client_state == mgr.websocket.client_state.CONNECTED:
            ws_lock = getattr(mgr, 'websocket_lock', None)
            if ws_lock:
                async with ws_lock:
                    await mgr.websocket.send_json(emotion_payload)
            else:
                await mgr.websocket.send_json(emotion_payload)
            logger.debug("[lumo_inject] emotion sent to frontend websocket char=%s", req.lanlan_name)
        else:
            logger.warning("[lumo_inject] websocket not connected, emotion only queued char=%s", req.lanlan_name)
    except Exception as e:
        # websocket 直发失败不影响 queue 入队结果（best-effort）
        logger.warning("[lumo_inject] emotion websocket direct-send failed char=%s: %s", req.lanlan_name, e)

    return {"success": True, "queued": True, "character": req.lanlan_name}


# ============ M4 Step3：任务桥接端点（H3/H4 鉴权链路） ============
# 数据流：陆墨 POST /api/lumo/task（LUMO_PROXY_TOKEN 鉴权）
#   → 本端点内部 HTTP POST agent_server /{tool}/run（NEKO_EXEC_TOKEN 鉴权）
#   → agent_server 执行 CUA/浏览器任务，返回 task_id
# 设计要点：
#   - 主 NEKO 与 agent_server 是不同端口的 HTTP 服务，必须走 HTTP 桥接
#   - NEKO_EXEC_TOKEN 与 LUMO_PROXY_TOKEN 分离（最小权限原则）
#   - 透传 agent_server 的 409(dedup)/429(背压)/503(不可用) 语义
#   - 审计日志只记 instruction 长度，不记全文（防泄露用户隐私指令）


class TaskRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=4096, description="任务指令")
    lanlan_name: Optional[str] = Field(None, max_length=64, description="目标角色名")
    tool: str = Field("computer_use", description="执行工具：computer_use | browser_use")
    screenshot_b64: Optional[str] = Field(None, max_length=2_000_000, description="可选截图 base64（CUA 用）")


def _resolve_neko_exec_token() -> str:
    """读取 NEKO_EXEC_TOKEN（仅环境变量源，与 LUMO_PROXY_TOKEN 分离）。"""
    return os.environ.get("NEKO_EXEC_TOKEN", "").strip()


@router.post("/task")
async def inject_task(req: TaskRequest, _auth: dict = Depends(require_proxy_token)):
    """陆墨任务注入 → NEKO agent_server 执行 CUA/浏览器任务。

    桥接路径复用 agent_server 的任务追踪/dedup/可用性检查基础设施。
    fail-safe：未配置 NEKO_EXEC_TOKEN 时返回 503 拒绝所有执行。
    """
    from config import TOOL_SERVER_PORT

    tool = (req.tool or "computer_use").strip().lower()
    if tool not in ("computer_use", "browser_use"):
        raise HTTPException(status_code=400, detail="invalid tool")

    exec_token = _resolve_neko_exec_token()
    if not exec_token:
        # 不泄露配置状态，用通用消息（与 require_exec_token 对齐）
        raise HTTPException(status_code=503, detail="service unavailable")

    payload: dict = {
        "instruction": req.instruction,
        "lanlan_name": req.lanlan_name,
    }
    if tool == "computer_use" and req.screenshot_b64:
        payload["screenshot_b64"] = req.screenshot_b64

    headers = {"Authorization": f"Bearer {exec_token}"}
    target = f"http://127.0.0.1:{TOOL_SERVER_PORT}/{tool}/run"

    # 沈遥 P0：computer_use 立即返回 task_id（30s 足够）；browser_use 同步等待执行完成（需 180s）
    bridge_timeout = 180.0 if tool == "browser_use" else 30.0
    try:
        client = _get_http_client()
        r = await client.post(target, json=payload, headers=headers, timeout=bridge_timeout)
    except httpx.RequestError as e:
        logger.warning("[lumo_inject] task bridge request error tool=%s: %s", tool, e)
        raise HTTPException(status_code=502, detail="agent unavailable")

    # 透传 agent_server 语义（与 api_routes.py 端点返回对齐）
    if r.status_code == 401:
        # 内部鉴权失败不应暴露给陆墨，统一为 502
        logger.error("[lumo_inject] task bridge internal auth rejected")
        raise HTTPException(status_code=502, detail="agent unavailable")
    if r.status_code == 429:
        raise HTTPException(status_code=429, detail="queue saturated", headers={"Retry-After": "1"})
    if r.status_code == 409:
        try:
            return JSONResponse(content=r.json(), status_code=409)
        except Exception:
            return JSONResponse(content={"success": False, "duplicate": True}, status_code=409)
    if r.status_code == 503:
        raise HTTPException(status_code=503, detail="service unavailable")
    if not r.is_success:
        logger.warning("[lumo_inject] task bridge unexpected status=%d tool=%s", r.status_code, tool)
        raise HTTPException(status_code=502, detail="agent unavailable")

    try:
        data = r.json()
    except Exception:
        data = {"success": True}

    # 审计日志：不记 instruction 全文（防泄露用户隐私指令），只记长度 + task_id
    logger.info(
        "[lumo_inject] action=task tool=%s char=%s instruction_len=%d task_id=%s",
        tool, req.lanlan_name, len(req.instruction), data.get("task_id"),
    )
    return data
