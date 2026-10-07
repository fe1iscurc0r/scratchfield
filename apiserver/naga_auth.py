"""
本地认证模块（陆墨定制版）
原 NagaBusiness 远程认证已替换为本地 Token 管理
双 Token 架构：access_token (30min) + refresh_token (7天)
refresh_token 由后端全权管理，前端仅持有 access_token
Token 加密方案：Electron SafeStorage → 降级 Fernet → 降级 PBKDF2

生产级加固：
- 使用 ContextVar 存储请求级 token，防止并发会话混淆
- 全局 token 仅用于后台任务和启动时恢复
"""

import asyncio
import base64
import contextvars
import hashlib
import hmac
import json
import logging
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
from cryptography.fernet import Fernet
from starlette.requests import Request

from system.config import get_config as _get_config
from system.config import get_data_dir
from apiserver.config import settings

logger = logging.getLogger(__name__)

_TOKEN_FILE = get_data_dir() / ".auth_session"

BUSINESS_URL = ""
NAGA_MODEL_URL = ""
NAGA_MEMORY_URL = ""

_ACCESS_TOKEN_TTL = 1800
_REFRESH_TOKEN_TTL = 604800

# 全局 token — 仅用于后台任务和启动时恢复
_access_token: str | None = None
_access_token_expires_at: float = 0.0
_refresh_token: str | None = None
_refresh_token_expires_at: float = 0.0
_user_info: dict | None = None
_refresh_lock = asyncio.Lock()
_last_refresh_at: float = 0.0
_REFRESH_GRACE_PERIOD: float = 10.0

# 登录失败限速（审计 LOW L4）：短时间多次失败后暂时锁定
_LOGIN_FAIL_LIMIT = 5
_LOGIN_FAIL_WINDOW = 300.0      # 5 分钟内允许 _LOGIN_FAIL_LIMIT 次失败
_LOGIN_LOCK_SECONDS = 300.0
_login_fail_count = 0
_login_fail_start: float = 0.0
_login_locked_until: float = 0.0

# 请求级 token — 使用 ContextVar 防止并发会话混淆
# 每个请求独立拥有自己的 token，互不干扰
_request_token: contextvars.ContextVar[str | None] = contextvars.ContextVar('request_token', default=None)
_request_user: contextvars.ContextVar[dict | None] = contextvars.ContextVar('request_user', default=None)


# ═══════════════════════════════════════════════════════════
# 跨平台文件权限保护
# ═══════════════════════════════════════════════════════════


def _set_secure_file_permission(file_path: Path):
    """设置文件为仅当前用户可读写（跨平台实现）
    
    Windows: 使用 icacls 设置 ACL 仅允许当前用户
    Unix: 使用 os.chmod 设置 0600 权限
    """
    try:
        if sys.platform == 'win32':
            username = settings.os_username()
            if username:
                subprocess.run(
                    ['icacls', str(file_path), '/inheritance:r', '/grant:r',
                     f'{username}:(R,W)'],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
        else:
            import stat as _stat
            os.chmod(file_path, _stat.S_IRUSR | _stat.S_IWUSR)
    except Exception as e:
        logger.debug(f"设置文件权限失败（非致命）: {e}")


# ═══════════════════════════════════════════════════════════
# 加密层：Electron SafeStorage → Fernet → PBKDF2 三级降级
# ═══════════════════════════════════════════════════════════

_FERNET_KEY_FILE = get_data_dir() / ".fernet_key"
_crypto_bridge_port: int | None = None
_bridge_auth_token: str | None = None


def _get_fernet_key() -> bytes:
    """获取或生成 Fernet 密钥，设置文件权限保护"""
    if _FERNET_KEY_FILE.exists():
        key = _FERNET_KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        _FERNET_KEY_FILE.write_bytes(key)
    _set_secure_file_permission(_FERNET_KEY_FILE)
    return key


_fernet = Fernet(_get_fernet_key())


def _fernet_encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def _fernet_decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


def _get_crypto_port() -> int | None:
    """读取 Electron SafeStorage 桥接端口（跨平台路径）"""
    global _crypto_bridge_port, _bridge_auth_token
    if _crypto_bridge_port is not None:
        return _crypto_bridge_port
    port_file = get_data_dir() / ".safe_storage_port"
    if port_file.exists():
        try:
            raw = port_file.read_text().strip()
            parts = raw.split("|")
            _crypto_bridge_port = int(parts[0])
            if len(parts) > 1:
                _bridge_auth_token = parts[1]
            return _crypto_bridge_port
        except Exception:
            pass
    _crypto_bridge_port = 0
    return None


async def _safe_encrypt(plaintext: str) -> str:
    """通过 Electron SafeStorage 加密，降级到 Fernet"""
    port = _get_crypto_port()
    if port:
        try:
            headers = {}
            if _bridge_auth_token:
                headers["X-Crypto-Token"] = _bridge_auth_token
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/crypto/encrypt",
                    json={"plaintext": plaintext},
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()["ciphertext"]
        except Exception as e:
            logger.warning(f"SafeStorage 加密失败，降级到 Fernet: {e}")
    return _fernet_encrypt(plaintext)


async def _safe_decrypt(ciphertext: str) -> str:
    """通过 Electron SafeStorage 解密，降级到 Fernet"""
    port = _get_crypto_port()
    if port:
        try:
            headers = {}
            if _bridge_auth_token:
                headers["X-Crypto-Token"] = _bridge_auth_token
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"http://127.0.0.1:{port}/crypto/decrypt",
                    json={"ciphertext": ciphertext},
                    headers=headers,
                )
                resp.raise_for_status()
                return resp.json()["plaintext"]
        except Exception as e:
            logger.warning(f"SafeStorage 解密失败，降级到 Fernet: {e}")
    return _fernet_decrypt(ciphertext)


# ═══════════════════════════════════════════════════════════
# Token 持久化（加密存储）
# ═══════════════════════════════════════════════════════════


async def _save_refresh_token():
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        plaintext = json.dumps({
            "refresh_token": _refresh_token,
            "expires_at": _refresh_token_expires_at,
        })
        encrypted = await _safe_encrypt(plaintext)
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=str(_TOKEN_FILE.parent), prefix='.auth_session_', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(encrypted)
            # 跨平台权限保护
            _set_secure_file_permission(Path(tmp_path))
            os.replace(tmp_path, str(_TOKEN_FILE))
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            raise
    except Exception as e:
        logger.warning(f"保存 refresh_token 失败: {e}")


async def _load_refresh_token():
    global _refresh_token, _refresh_token_expires_at
    if not _TOKEN_FILE.exists():
        return
    try:
        encrypted = _TOKEN_FILE.read_text()
        plaintext = await _safe_decrypt(encrypted)
        data = json.loads(plaintext)
        _refresh_token = data.get("refresh_token")
        _refresh_token_expires_at = data.get("expires_at", 0)
        if _refresh_token and _refresh_token_expires_at > time.time():
            logger.info("从加密文件恢复 refresh_token 成功")
        else:
            _refresh_token = None
            logger.info("refresh_token 已过期，清除")
    except Exception as e:
        logger.warning(f"加载 refresh_token 失败: {e}")


def _clear_refresh_token():
    global _refresh_token, _refresh_token_expires_at
    _refresh_token = None
    _refresh_token_expires_at = 0.0
    try:
        if _TOKEN_FILE.exists():
            _TOKEN_FILE.unlink()
    except Exception as e:
        logger.warning(f"删除 refresh_token 文件失败: {e}")


def _generate_access_token() -> str:
    global _access_token, _access_token_expires_at
    _access_token = secrets.token_urlsafe(32)
    _access_token_expires_at = time.time() + _ACCESS_TOKEN_TTL
    return _access_token


def _generate_refresh_token() -> str:
    global _refresh_token, _refresh_token_expires_at
    _refresh_token = secrets.token_urlsafe(32)
    _refresh_token_expires_at = time.time() + _REFRESH_TOKEN_TTL
    asyncio.create_task(_save_refresh_token())
    return _refresh_token


def _is_token_valid() -> bool:
    if not _access_token:
        return False
    if time.time() > _access_token_expires_at:
        return False
    return True


def should_use_model_gateway() -> bool:
    """判断是否应使用 NagaModel 网关：需同时满足「已登录」与「配置启用 use_gateway」。"""
    if not is_authenticated():
        return False
    # 通过模块属性访问 get_config，确保 unittest.mock.patch('system.config.get_config') 生效
    import system.config as _sc
    cfg = _sc.get_config()
    return getattr(getattr(cfg, 'api', None), 'use_gateway', False)


# 不再使用模块级同步加载 — 改为 lifespan 异步加载
# _load_refresh_token()


# ═══════════════════════════════════════════════════════════
# 鉴权逻辑
# ═══════════════════════════════════════════════════════════


def is_auth_required() -> bool:
    """本地鉴权是否启用（require_auth=True）。

    未启用时所有请求应直接放行（与 require_local_auth 语义一致），
    供 API 中间件判断是否跳过 token 校验。
    """
    _, _, _, require_auth = _load_auth_config()
    return bool(require_auth)


def _load_auth_config() -> tuple:
    """加载鉴权配置，返回 (username, password_hash, salt, require_auth)"""
    try:
        cfg = _get_config()
        auth_cfg = getattr(cfg, 'auth', None)
        if auth_cfg:
            return (
                auth_cfg.username or "admin",
                auth_cfg.password_hash or "",
                auth_cfg.password_salt or "",
                auth_cfg.require_auth,
            )
    except Exception:
        pass
    return ("admin", "", "", False)


async def get_captcha(format_type: str = "") -> dict:
    return {
        "captcha_id": secrets.token_hex(8),
        "captcha_answer": "local",
        "image_data": None,
    }


async def login(username: str, password: str, captcha_id: str = "", captcha_answer: str = "") -> dict:
    global _user_info, _login_fail_count, _login_fail_start, _login_locked_until

    # 登录失败限速：锁定期内直接拒绝（审计 LOW L4）
    now = time.time()
    if now < _login_locked_until:
        raise ValueError("登录尝试过于频繁，请稍后再试")
    if _login_fail_count >= _LOGIN_FAIL_LIMIT and (now - _login_fail_start) < _LOGIN_FAIL_WINDOW:
        _login_locked_until = now + _LOGIN_LOCK_SECONDS
        _login_fail_count = 0
        raise ValueError("登录尝试过于频繁，请 5 分钟后再试")

    def _note_failure() -> None:
        global _login_fail_count, _login_fail_start
        nonlocal now
        if _login_fail_count == 0:
            _login_fail_start = now
        _login_fail_count += 1

    if not username:
        raise ValueError("用户名不能为空")

    auth_user, auth_hash, auth_salt, require_auth = _load_auth_config()

    if auth_hash and auth_salt:
        if username != auth_user:
            _note_failure()
            raise ValueError("用户名或密码错误")
        if password:
            from system.config import _hash_password as _hp
            check_hash, _ = _hp(password, auth_salt)
            if not hmac.compare_digest(check_hash, auth_hash):
                _note_failure()
                raise ValueError("用户名或密码错误")
        elif require_auth:
            _note_failure()
            raise ValueError("密码不能为空")

    # 登录成功，重置失败计数
    _login_fail_count = 0
    _login_fail_start = 0.0
    _login_locked_until = 0.0

    _generate_access_token()
    _generate_refresh_token()
    _user_info = {"username": username}

    return {
        "success": True,
        "user": _user_info,
        "access_token": _access_token,
        "memory_url": NAGA_MEMORY_URL,
    }


async def get_me(token: str | None = None) -> dict | None:
    """获取当前请求用户信息（支持请求级上下文）"""
    # 优先从请求级上下文获取
    ctx_user = _request_user.get()
    if ctx_user:
        return ctx_user
    # 回退到全局 token 验证
    if token == _access_token and _is_token_valid():
        return _user_info
    return None


def set_request_context(token: str, user: dict | None = None):
    """设置当前请求的鉴权上下文（由中间件调用）"""
    _request_token.set(token)
    if user:
        _request_user.set(user)


def get_request_token() -> str | None:
    """读取当前请求的鉴权上下文 token（中间件校验通过后才有值）"""
    return _request_token.get()


def clear_request_context():
    """清除当前请求的鉴权上下文"""
    _request_token.set(None)
    _request_user.set(None)


async def refresh() -> dict:
    global _access_token, _last_refresh_at
    async with _refresh_lock:
        if not _refresh_token:
            raise ValueError("无可用的 refresh_token，请重新登录")

        if time.time() > _refresh_token_expires_at:
            _clear_refresh_token()
            raise ValueError("refresh_token 已过期，请重新登录")

        _generate_access_token()
        _last_refresh_at = time.monotonic()

        return {"access_token": _access_token}


def logout():
    global _access_token, _user_info, _access_token_expires_at
    _access_token = None
    _access_token_expires_at = 0.0
    _user_info = None
    _clear_refresh_token()


def is_authenticated() -> bool:
    return _is_token_valid()


def has_refresh_token() -> bool:
    return _refresh_token is not None and _refresh_token_expires_at > time.time()


def restore_token(token: str):
    """恢复 token — 支持请求级上下文，防止并发竞态"""
    if not token:
        return
    # 设置请求级上下文（如果在请求上下文中）
    try:
        set_request_context(token)
    except LookupError:
        pass  # 不在请求上下文中，回退到全局
    # 同时更新全局（用于后台任务兼容性）
    global _access_token
    if _last_refresh_at and (time.monotonic() - _last_refresh_at < _REFRESH_GRACE_PERIOD):
        if token != _access_token:
            return
    _access_token = token
    _access_token_expires_at = time.time() + _ACCESS_TOKEN_TTL


def get_access_token() -> str | None:
    """获取当前有效 token — 优先请求级"""
    # 优先从请求级上下文获取
    ctx_token = _request_token.get()
    if ctx_token:
        return ctx_token
    # 回退到全局 token
    if not _is_token_valid():
        return None
    return _access_token


async def ensure_access_token():
    global _access_token
    if _is_token_valid():
        return
    if _refresh_token and _refresh_token_expires_at > time.time():
        try:
            await refresh()
            logger.info("ensure_access_token: 自动刷新成功")
        except Exception as e:
            logger.error(f"ensure_access_token: 自动刷新失败: {e}")
    else:
        logger.info("ensure_access_token: 无可用 refresh_token，跳过")


def get_user_info() -> dict | None:
    return _user_info


async def register(username: str, email: str, password: str, verification_code: str) -> dict:
    """注册：首次使用时设置密码"""
    if not username or not password:
        raise ValueError("用户名和密码不能为空")

    auth_user, auth_hash, auth_salt, _ = _load_auth_config()
    if auth_hash:
        raise ValueError("系统已配置密码，请使用登录")

    from system.config import _hash_password as _hp
    from system.config_manager import update_config
    pw_hash, salt = _hp(password)

    update_config({
        "auth": {
            "username": username,
            "password_hash": pw_hash,
            "password_salt": salt,
            "require_auth": True,
        }
    })

    return {"success": True, "username": username, "email": email}


async def send_verification(email: str, username: str, captcha_id: str = "", captcha_answer: str = "") -> dict:
    return {"success": True, "message": "本地模式：邮箱验证已跳过"}


async def send_qq_verification(
    email: str,
    access_token: str,
    captcha_id: str = "",
    captcha_answer: str = "",
) -> dict:
    return {"success": True, "message": "本地模式：QQ验证已跳过"}


async def bind_qq_email(
    email: str,
    verification_code: str,
    access_token: str,
) -> dict:
    return {"success": True, "message": "本地模式：QQ绑定已跳过"}


# ============ FastAPI 鉴权依赖 ============


async def require_local_auth(request: Request) -> dict | None:
    """本地鉴权依赖 - 检查请求是否已认证
    
    行为：
    - 若 require_auth=False，直接放行（本地模式）
    - 若 require_auth=True，检查 Authorization 头中的 Bearer Token
    - Token 有效则返回用户信息，无效则抛出 401
    
    用法：在路由函数参数中添加 auth: dict = Depends(require_local_auth)
    """
    auth_user, auth_hash, auth_salt, require_auth = _load_auth_config()
    
    if not require_auth:
        return {"username": "local_user", "auth_required": False}
    
    # 检查 Authorization 头
    auth_header = request.headers.get("authorization", "")
    token = None
    
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    
    if not token:
        # 尝试从 Cookie 恢复
        token = request.cookies.get("access_token")
    
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录，请先认证")
    
    # 验证 token
    token_data = _verify_token(token)
    if not token_data:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    
    return {
        "username": token_data.get("username", "unknown"),
        "auth_required": True,
        "token": token,
    }


def _verify_token(token: str) -> dict | None:
    """验证 token 有效性"""
    global _access_token, _access_token_expires_at, _user_info
    
    # 检查是否与当前有效 token 匹配
    if token == _access_token and _is_token_valid():
        return _user_info or {"username": "user"}
    
    # 尝试解析 token（简化版，实际应由 JWT 或 Fernet 签名验证）
    try:
        import base64
        import json

        from system.config import get_data_dir
        
        # 简单 token 格式检查：token 应为非空字符串
        if not token or len(token) < 16:
            return None
        
        # 检查过期时间
        if _access_token_expires_at > 0 and time.time() > _access_token_expires_at:
            return None
        
        # 检查是否是已知 token
        if token == _access_token:
            return _user_info or {"username": "user"}
        
        return None
    except Exception:
        return None
