#!/usr/bin/env bash
# 下载本地 kokoro-onnx 引擎模型（离线 TTS 兜底用）。
# 用法：
#   bash scripts/download_kokoro_models.sh           # 中文
#   bash scripts/download_kokoro_models.sh en-us     # 英文
set -euo pipefail

LANG="${1:-zh}"
BASE="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"

# 目标目录：数据目录 models/kokoro（可从主仓 config 覆盖）
DEST="${KOKORO_MODELS_DIR:-$(pwd)/models/kokoro}"
mkdir -p "$DEST"

case "$LANG" in
  zh)
    MODEL="kokoro-v1.1-zh.onnx"; VOICES="voices-v1.1-zh.bin";;
  en-us)
    MODEL="kokoro-v1.1.onnx"; VOICES="voices-v1.1.bin";;
  *)
    echo "不支持的语言: $LANG（用 zh 或 en-us）" >&2; exit 1;;
esac

echo "下载模型到 $DEST"
curl -fL --retry 3 -o "$DEST/kokoro.onnx" "$BASE/$MODEL"
curl -fL --retry 3 -o "$DEST/voices.bin" "$BASE/$VOICES"
# config.json 词表复用引擎内置，无需联网
if [ -f "$(dirname "$0")/../../vendor/kokoro-onnx/kokoro_onnx/config.json" ]; then
  cp "$(dirname "$0")/../../vendor/kokoro-onnx/kokoro_onnx/config.json" "$DEST/config.json"
  echo "config.json 已从引擎内置词表复制"
fi

echo "完成。模型在 $DEST"
ls -lh "$DEST"