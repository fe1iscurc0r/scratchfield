#!/usr/bin/env bash
# 统一树启动脚本 v2 —— 完全独立：只使用 unified 树内的环境
# 用法：bash _start_all.sh   （必须托管后台；父任务退出即全停）
# 五端：后端 8000/8001/8003 · Web 5173 · NEKO 48911 · NEKO 桌宠 · Lumo 桌面窗口
set -u

NODE="C:/Users/ASUS/.workbuddy/binaries/node/versions/22.22.2-6/node.exe"
NPM="C:/Users/ASUS/AppData/Local/Microsoft/WinGet/Packages/OpenJS.NodeJS.22_Microsoft.Winget.Source_8wekyb3d8bbwe/node-v22.23.2-win-x64/npm.cmd"
U="/d/my git/scratchpad-unified"

mkdir -p "$U/build"

SP_PY="$U/.venv/Scripts/python.exe"                  # 3.12 · 后端
NEKO_PY="$U/NEKO/N.E.K.O/.venv/Scripts/python.exe"   # 3.11 · NEKO

[ -x "$SP_PY" ]   || { echo "缺少后端 venv: $SP_PY"; exit 1; }
[ -x "$NEKO_PY" ] || { echo "缺少 NEKO venv: $NEKO_PY"; exit 1; }
[ -d "$U/frontend/node_modules" ] || { echo "缺少 frontend/node_modules"; exit 1; }

# [0/4] 自愈：Live2D 默认模型 yui-lolita 未展开会导致桌宠空白（transparent overlay 里什么都不画）。
# 上游把模型打成 assets/yui-lolita.tar.gz，NEKO 的 find_models() 会扫 static/，故解到 static/ 即可被发现。
# 幂等：已存在则跳过。
YU="$U/NEKO/N.E.K.O/static/yui-lolita"
if [ ! -d "$YU" ] && [ -f "$U/NEKO/N.E.K.O/assets/yui-lolita.tar.gz" ]; then
  echo "[0/4] 展开 Live2D 模型 yui-lolita → static/"
  mkdir -p "$U/NEKO/N.E.K.O/static"
  tar -xzf "$U/NEKO/N.E.K.O/assets/yui-lolita.tar.gz" -C "$U/NEKO/N.E.K.O/static" || echo "  ⚠️ 模型解包失败（桌宠会空白）"
fi

# [0.5/4] 自愈：React 聊天窗产物（static/react/neko-chat/*）由 frontend/react-neko-chat 构建，**不入库**；
# 每次从 tarball 同步后必然丢失 ⇒ 聊天框报「资源加载失败」（neko-chat-window.iife.js/.css 双 404）。
RC="$U/NEKO/N.E.K.O/static/react/neko-chat/neko-chat-window.iife.js"
if [ ! -f "$RC" ]; then
  echo "[0.5/4] 构建 React 聊天窗（首次约 20-60s）"
  (
    cd "$U/NEKO/N.E.K.O/frontend/react-neko-chat" || exit 1
    [ -d node_modules ] || env -u NODE_OPTIONS "$NPM" install --no-audit --no-fund
    env -u NODE_OPTIONS "$NPM" run build
  ) > "$U/build/_react_chat_build.log" 2>&1 \
    || echo "  ⚠️ 构建失败，聊天框会缺资源：看 build/_react_chat_build.log"
fi

echo "[1/5] 后端 8000/8001/8003（首次启动约 2 分钟）"
( cd "$U" && "$SP_PY" main.py --headless > build/_serve.log 2>&1 ) &

echo "[2/5] Web 前端 5173"
( cd "$U/frontend" && env -u NODE_OPTIONS WEB_ONLY=1 "$NODE" node_modules/vite/bin/vite.js \
    --port 5173 --strictPort > ../build/_vite.log 2>&1 ) &

echo "[3/5] NEKO 主服务 48911"
( cd "$U/NEKO/N.E.K.O" && env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    "$NEKO_PY" -m app.main_server > ../../build/_neko.log 2>&1 ) &

# NEKO 是**双服务**：主服务 48911 + tool_server(agent_server) 48915（并自带用户插件服务 48916）。
# 只起 48911 时，主服务的 /api/agent/* 全部代理失败返回 502 "proxy error: ..."（实测 11 个端点）。
echo "[3.5/5] NEKO tool_server 48915（+ 插件服务 48916）"
( cd "$U/NEKO/N.E.K.O" && env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    "$NEKO_PY" -m app.agent_server > ../../build/_neko_agent.log 2>&1 ) &

sleep 130   # 后端首启动慢（openclaw vendor + Vault 索引）

echo "[4/5] NEKO 桌宠（SwiftShader 软件 WebGL）"
# ⚠️ 不要用 --disable-gpu/--disable-software-rasterizer：会把 WebGL 一起关掉，
#    Live2D 报 "WebGL unsupported" ⇒ 透明 overlay 里什么都画不出来（表现为"桌宠不见了"）。
( cd "$U/neko-electron-shell" && env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    "$NODE" node_modules/electron/cli.js \
    --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader . > ../build/_neko_shell.log 2>&1 ) &

echo "[5/5] Lumo 桌面窗口（Electron + 自身后端）"
# vite 用 WEB_ONLY 起（否则 vite-plugin-electron 会以默认参数拉起 electron，本机 GPU 进程会崩）；
# 这里显式用 SwiftShader 起窗口，Live2D 才能拿到 WebGL 2。
( cd "$U/frontend" && env -u ELECTRON_RUN_AS_NODE -u NODE_OPTIONS \
    VITE_DEV_SERVER_URL="http://localhost:5173" \
    "$NODE" node_modules/electron/cli.js \
    --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader . > ../build/_lumo_app.log 2>&1 ) &

echo "五端已拉起，等待子进程…"
wait
