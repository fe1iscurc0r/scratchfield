import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # 加入项目根目录到模块查找路径
# utils.py
from functools import wraps

from fastapi import Request
from fastapi.responses import JSONResponse

from system.config import config  # 使用统一配置系统

DEFAULT_LANGUAGE = config.tts.default_language # 统一配置


def getenv_bool(key: str, default: bool = False) -> bool:
    """从环境变量获取布尔值"""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

API_KEY = config.tts.api_key
REQUIRE_API_KEY = config.tts.require_api_key
DETAILED_ERROR_LOGGING = getenv_bool('DETAILED_ERROR_LOGGING', True)

def require_api_key(f):
    @wraps(f)
    async def decorated_function(request: Request, *args, **kwargs):
        if not REQUIRE_API_KEY:
            return await f(request, *args, **kwargs)
        # 安全：启用鉴权但未配置 API_KEY 时拒绝服务，避免空密钥被空 token 绕过
        if not API_KEY:
            return JSONResponse({"error": "API key not configured on server"}, status_code=401)
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JSONResponse({"error": "Missing or invalid API key"}, status_code=401)
        token = auth_header.split('Bearer ')[1]
        if token != API_KEY:
            return JSONResponse({"error": "Invalid API key"}, status_code=401)
        return await f(request, *args, **kwargs)
    return decorated_function

# Mapping of audio format to MIME type
AUDIO_FORMAT_MIME_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/L16"
}
