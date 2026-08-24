#!/usr/bin/env bash
# sdrtrunk sidecar（W-01）容器验收入口 —— simulate 模式（零 JVM 依赖）
#
# 由 Dockerfile 的 CMD 调用。执行两步：
#   1) 单元测试：mcpserver/rf_brain/test_sdrtrunk_bridge.py（10 项）
#   2) 验收脚本：合成 P25 WAV → SdrtrunkBridge(simulate) 过桥 → 结构化 JSON 落 /out
# live 探测（真 sdrtrunk JVM）需在 build 时传入 SDRTRUNK_ZIP_URL/JMBE_ZIP_URL，
# 容器内另有 /opt/sdrtrunk 与 /opt/jmbe，可另行编排 Java 启动。
set -euo pipefail

export PYTHONPATH=/app

echo "== [1/2] 单元测试 =="
python3 -m pytest -q mcpserver/rf_brain/test_sdrtrunk_bridge.py

echo "== [2/2] W-01 验收脚本（模拟 P25 WAV 过桥 → 结构化 JSON）=="
mkdir -p /out
python3 mcpserver/rf_brain/sdrtrunk_bridge/accept_sdrtrunk_bridge.py /out/accept_out.json

echo
echo "== 容器验收全部通过 =="
