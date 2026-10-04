import json
import os
import pathlib
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from system.config import config
from system.cors_config import LOCAL_ORIGIN_REGEX  # 复用统一正则字符串（非 apply_local_cors，因 TTS 需更严格方法限制）
from voice.output.tts_handler import _generate_audio
from voice.output.utils import AUDIO_FORMAT_MIME_TYPES, require_api_key

app = FastAPI()

# 统一 CORS 配置（TTS服务限制POST方法）
# 注意：allow_origin_regex 必须是字符串，Starlette 内部会 re.compile；
#       早期写成 list[Pattern] 会触发 TypeError: unhashable type: 'list'
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=LOCAL_ORIGIN_REGEX,  # 字符串，匹配 http/https + 本机 + 任意端口
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],  # TTS 仅需 POST，比通用配置更严格
    allow_headers=["Authorization", "Content-Type"],
)

# ── 只读接口：对齐 OpenAI 兼容 TTS-API 形状 ──
# 目的：让 MCP 侧的 tts_api 适配器（走 OpenAI 兼容契约：GET / 探活、GET /v1/audio/voices 列音色、
# POST /v1/audio/speech 合成）可以直接指向本机 TTS，而不必另起一个第三方 TTS-API 服务。
# 注意：本地服务只监听 127.0.0.1，且 GET 接口不要求鉴权（与 POST 的 @require_api_key 独立）。


def _character_voices() -> dict[str, str]:
    """角色名 → 配音音色（读 characters/<角色>/<角色>.json 的 voice 字段）。"""
    voices: dict[str, str] = {}
    root = pathlib.Path(__file__).resolve().parents[2] / "characters"
    if not root.exists():
        return voices
    for char_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for cfg_file in sorted(char_dir.glob("*.json")):
            if cfg_file.name.endswith("chara_card_v3.json"):
                continue
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            voice = str((data or {}).get("voice") or "").strip()
            if voice:
                voices[char_dir.name] = voice
                break
    return voices


@app.get('/')
async def tts_root_info():
    """服务信息 / 健康检查（tts_api 适配器的 tts_health 打的就是 GET /）。"""
    return {
        "status": "ok",
        "service": "lumo-tts",
        "engine": "edge-tts",
        "default_voice": config.tts.default_voice,
        "default_format": config.tts.default_format,
        "auth_required": bool(getattr(config.tts, "require_api_key", False)),
        "endpoints": ["/v1/audio/speech", "/v1/audio/voices"],
    }


@app.get('/v1/audio/voices')
async def list_voices():
    """可用音色列表（OpenAI 兼容形状）：默认音色 + 各角色配音。"""
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(voice_id: str, note: str) -> None:
        if not voice_id or voice_id in seen:
            return
        seen.add(voice_id)
        parts = voice_id.split("-")
        locale = "-".join(parts[:2]) if len(parts) >= 2 else ""
        entries.append({
            "id": voice_id,
            "name": voice_id,
            "engine": "edge",
            "locale": locale,
            "note": note,
        })

    _add(config.tts.default_voice, "默认音色")
    for char_name, voice_id in _character_voices().items():
        _add(voice_id, f"角色 {char_name}")
    return {"object": "list", "data": entries}


@app.post('/v1/audio/speech')
@require_api_key
async def text_to_speech(request: Request):
    try:
        data = await request.json()
        if not data or 'input' not in data:
            return JSONResponse({"error": "Missing 'input' in request body"}, status_code=400)

        text = data.get('input')
        voice = data.get('voice', config.tts.default_voice)
        response_format = data.get('response_format', 'mp3')
        speed = float(data.get('speed', config.tts.default_speed))

        mime_type = AUDIO_FORMAT_MIME_TYPES.get(response_format, "audio/mpeg")
        output_file_path = await _generate_audio(text, voice, response_format, speed)
        # 本地引擎回退可能返回 wav，按实际文件后缀归一化 mime
        actual_suffix = os.path.splitext(output_file_path)[1].lstrip('.').lower()
        if actual_suffix and actual_suffix in AUDIO_FORMAT_MIME_TYPES:
            mime_type = AUDIO_FORMAT_MIME_TYPES[actual_suffix]
        # 响应发送完成后删除临时音频文件，避免长期积累占满磁盘
        return FileResponse(
            output_file_path,
            media_type=mime_type,
            filename="speech.mp3",
            background=BackgroundTask(os.unlink, output_file_path),
        )
    except Exception as e:
        from system.config import get_data_dir
        error_log = get_data_dir() / "logs" / "voice_server_error.log"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        # 审计 LOW L5: 限制错误日志无界增长，超 1MB 先清空再写
        try:
            if error_log.exists() and error_log.stat().st_size > 1_048_576:
                error_log.write_text("", encoding="utf-8")
        except OSError:
            pass
        with open(error_log, 'a', encoding='utf-8') as f:
            f.write(f"Error at {__name__}: {str(e)}\n")
            import traceback
            traceback.print_exc(file=f)
        return JSONResponse({"error": "An internal server error occurred."}, status_code=500)

if __name__ == '__main__':
    import uvicorn
    # 安全：仅绑定 loopback
    uvicorn.run(app, host='127.0.0.1', port=config.tts.port)
