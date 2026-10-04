"""
统一 CORS 配置 - 所有服务引用此模块确保一致性

设计说明：
- Starlette 的 CORSMiddleware 要求 `allow_origin_regex` 为 **字符串**（内部会 re.compile）
- 早期实现把 list[Pattern] 传进去会触发 `TypeError: unhashable type: 'list'`
- 现合并为单条正则：匹配 http/https + 127.0.0.1/localhost + 任意端口
- 用锚定符 `^...$` 防止子串绕过（如 https://localhost.evil.com:8080）
"""

# 允许的本地源正则（字符串形式，传给 CORSMiddleware.allow_origin_regex）
# 匹配示例：
#   http://127.0.0.1:5173
#   https://localhost:8000
#   lumo-app://dist            （Electron 构建版页面源：loadURL('lumo-app://dist/index.html')）
# 不匹配：
#   http://localhost.evil.com:8080  （被 $ 锚定符挡住）
#   file://127.0.0.1:8000           （协议不符）
#
# Electron 补充说明：构建版窗口的 Origin 是自定义协议 lumo-app://dist，不带端口，
# 早期正则只认 http(s)://localhost:port，导致构建版所有 /system/* 请求被 CORS 拦下
# （实测：渲染进程报 "blocked by CORS policy: No 'Access-Control-Allow-Origin'"，
# 应用卡在启动 10%）。补 lumo-app 与 file 两条本地壳来源。
LOCAL_ORIGIN_REGEX = (
    r"^(https?://(127\.0\.0\.1|localhost):\d+"
    r"|lumo-app://[A-Za-z0-9._-]+"
    r"|file://)$"
)


def apply_local_cors(app):
    """为 FastAPI 应用添加统一的本地 CORS 配置

    参数：
        app: FastAPI 实例
    说明：
        - 仅允许本机源（127.0.0.1 / localhost + 任意端口，http/https 均支持）
        - 允许携带凭证（cookie / Authorization）
        - 放行常见方法（含 OPTIONS 预检）和必要头
    """
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=LOCAL_ORIGIN_REGEX,  # 必须是字符串，不能是 list/Pattern
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
    )
