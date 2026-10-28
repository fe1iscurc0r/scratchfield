#!/usr/bin/env bash
# psd2live MIT 段桥接脚本（工单 263 任务 B）
#
# 只调用上游 **MIT 段**：
#   format-model  中立绑定 IR
#   format-compile 导出框架
#   runtime/      Rust 运行时（.p2lrt 播放）
# **不调用、不链接、不打包** 引擎 umamo（GPL-3.0）与 Cubism/PSD 导出目标。
#
# 本脚本不联网、不 clone；上游路径必须由使用者显式传入。
set -euo pipefail

UPSTREAM=""
INPUT=""
OUT_DIR=""
TARGET="p2lrt"

usage() {
  cat <<'EOF'
用法: cli.sh --upstream <psd2live 本地路径> --input <IR.json> --out <输出目录> [--target p2lrt]

  --upstream  已 clone 的 psd2live 仓库根目录（本脚本不负责下载）
  --input     中立绑定 IR（format-model 产物，JSON）
  --out       输出目录
  --target    导出目标（默认 p2lrt，MIT 段）

退出码: 0 成功 / 2 参数错误 / 3 上游缺少 MIT 段 / 4 上游含 GPL 段被拒
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upstream) UPSTREAM="${2:-}"; shift 2 ;;
    --input)    INPUT="${2:-}";    shift 2 ;;
    --out)      OUT_DIR="${2:-}";  shift 2 ;;
    --target)   TARGET="${2:-}";   shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 2 ;;
  esac
done

[[ -n "$UPSTREAM" && -n "$INPUT" && -n "$OUT_DIR" ]] || { usage; exit 2; }
[[ -d "$UPSTREAM" ]] || { echo "上游路径不存在: $UPSTREAM" >&2; exit 2; }
[[ -f "$INPUT" ]]    || { echo "IR 文件不存在: $INPUT" >&2; exit 2; }

# --- 许可护栏：确认所需 MIT 段存在，且**不**进入 GPL 段 ---
for seg in format-model format-compile; do
  [[ -d "$UPSTREAM/$seg" ]] || { echo "上游缺少 MIT 段: $seg" >&2; exit 3; }
done
if [[ -d "$UPSTREAM/umamo" ]]; then
  echo "[bridge] 检测到 umamo/（GPL-3.0）：本工具不调用、不链接，仅提示其存在。" >&2
fi

mkdir -p "$OUT_DIR"
echo "[bridge] upstream : $UPSTREAM"
echo "[bridge] IR       : $INPUT"
echo "[bridge] target   : $TARGET (MIT 段)"
echo "[bridge] out      : $OUT_DIR"
echo
echo "[bridge] 典型调用（需上游已构建；本脚本不代为构建）:"
echo "  (cd \"$UPSTREAM\" && ./gradlew :format-compile:run --args=\"--in '$INPUT' --out '$OUT_DIR' --target $TARGET\")"
echo
echo "[bridge] 本脚本不执行上述命令（禁止在此静默构建/联网）；请人工确认后执行。"
echo "[bridge] 完成（dry-run）。"
