#!/usr/bin/env bash
# ============================================================
#  scratchpad 一键部署（Linux / macOS 骨架版，卷165 仅骨架）
#
#  用法：
#     ./setup.sh                 # 自检 → uv sync → 前端 npm install
#     ./setup.sh --extras pdf2md # 额外装 pdf2md extra
#     ./setup.sh --skip-build    # 只装依赖不构建
#
#  说明：本卷（卷165）以 Windows 为优先目标，setup.ps1 是完整实现；
#        这里只做等价骨架：自检 → 后端 → 前端，任一步失败即停。
#        检测逻辑本身跨平台（doctor_env.py 纯标准库 + subprocess），三平台通用。
# ============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

EXTRAS=""
SKIP_BUILD=0
while [ $# -gt 0 ]; do
  case "$1" in
    --extras) EXTRAS="${2:-}"; shift 2 ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    *) echo "未知参数: $1"; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }
fail() { printf '\n[失败] %s\n[停] 不继续后续步骤。\n' "$1" >&2; exit 1; }

# ---------------- 1/4 环境自检 ----------------
step "1/4 环境自检（doctor_env.py）"
command -v python >/dev/null 2>&1 || fail "未找到 python。请先安装 Python 3.12.x（严格 3.12，非 3.13）。"
python "$REPO_ROOT/doctor_env.py" || fail "环境自检未通过：按上面列出的【缺失】项装完再重跑。"

# ---------------- 2/4 后端依赖 ----------------
step "2/4 后端依赖（uv sync）"
UV_ARGS=(sync)
if [ -n "$EXTRAS" ]; then
  IFS=',' read -ra EXTRA_LIST <<< "$EXTRAS"
  for e in "${EXTRA_LIST[@]}"; do
    e="$(echo "$e" | xargs)"
    [ -n "$e" ] && UV_ARGS+=(--extra "$e")
  done
fi
echo "    uv ${UV_ARGS[*]}"
uv "${UV_ARGS[@]}" || fail "uv sync 失败（错误见上方原样输出）。"

# ---------------- 3/4 前端 ----------------
step "3/4 前端（frontend/）"
[ -d "$REPO_ROOT/frontend" ] || fail "找不到 frontend 目录"
cd "$REPO_ROOT/frontend"
if [ -d node_modules ]; then
  echo "    node_modules 已存在，跳过 npm install"
else
  npm install || fail "npm install 失败（本仓有 package-lock.json，请只用 npm）。"
fi
if [ "$SKIP_BUILD" -eq 1 ]; then
  echo "    已指定 --skip-build，跳过构建（开发时用 npm run dev）"
else
  npm run build || fail "前端构建失败。"
fi
cd "$REPO_ROOT"

# ---------------- 4/4 收尾 ----------------
step "4/4 安装完成"
LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$LAN_IP" ] && LAN_IP="<本机局域网IP>"
cat <<EOF

启动方式（二选一）：
  桌面端：  python main.py
  纯 web：  uv run uvicorn apiserver.api_server:app --host 0.0.0.0 --port 8000

局域网访问（平板/手机浏览器）：
  http://$LAN_IP:5173/   前端 dev（先 cd frontend; npm run dev）
  http://$LAN_IP:8000/   后端 API（--host 0.0.0.0 才对局域网开放）

环境依赖细节见 docs/环境依赖清单-Windows装机-2026-09-27.md
EOF
