import os
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
