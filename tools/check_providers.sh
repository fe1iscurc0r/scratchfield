#!/bin/sh
# 工单229 任务三 · 模型 ID 兼容矩阵巡检入口
#
# 真调各 provider 的 default 模型，验证「model ID 能原样回传」（防 alias 漂移）。
# 没有 key 的 provider 会被 skip，**不算失败**；退出码 = pytest 退出码（0 = 全过）。
#
# 用法：
#   tools/check_providers.sh                   # 全量巡检
#   tools/check_providers.sh -k deepseek       # 只跑某一支（透传 pytest 参数）
#   PYTHON_BIN=/path/to/python tools/check_providers.sh
#   SKIP_LIVE_API_TEST=1 tools/check_providers.sh    # 全部跳过（应全 skip、exit 0）
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(dirname -- "$HERE")
PYTHON_BIN="${PYTHON_BIN:-python}"

cd "$ROOT"
exec "$PYTHON_BIN" -m pytest -m live tests/test_provider_model_id.py -q "$@"
