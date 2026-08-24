#!/usr/bin/env python3
"""
语音服务启动脚本
支持HTTP模式
"""
import argparse
import os
import sys

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from system.config import config


def start_http_server():
    """启动HTTP语音输出服务器"""
    try:
        import uvicorn

        from voice.output.server import app

        print("🚀 启动HTTP语音输出服务器...")
        print(f"📍 地址: http://127.0.0.1:{config.tts.port}")
        print(f"🔑 API密钥: {'已启用' if config.tts.require_api_key else '已禁用'}")

        # 安全：仅绑定 loopback，TTS 服务仅供本机前端/后端调用
        uvicorn.run(app, host='127.0.0.1', port=config.tts.port)

    except Exception as e:
        print(f"❌ HTTP语音输出服务器启动失败: {e}")
        return False

def check_dependencies():
    """检查依赖是否安装"""
    missing_deps = []

    try:
        import edge_tts
    except ImportError:
        missing_deps.append("edge-tts")

    try:
        import emoji
    except ImportError:
        missing_deps.append("emoji")

    try:
        import librosa
    except ImportError:
        missing_deps.append("librosa")

    try:
        import soundfile
    except ImportError:
        missing_deps.append("soundfile")

    if missing_deps:
        print(f"❌ 缺少依赖: {', '.join(missing_deps)}")
        print("请运行: pip install " + " ".join(missing_deps))
        return False

    return True

def main():
    parser = argparse.ArgumentParser(description="语音服务启动器")
    parser.add_argument("--port", type=int, help="自定义端口")
    parser.add_argument("--check-deps", action="store_true", help="检查依赖")

    args = parser.parse_args()

    if args.check_deps:
        if check_dependencies():
            print("✅ 所有依赖已安装")
        return

    # 检查依赖
    if not check_dependencies():
        return

    # 设置端口
    if args.port:
        config.tts.port = args.port

    print("=" * 50)
    print("🎤 NagaAgent 语音输出服务")
    print("=" * 50)
    print("📋 配置信息:")
    print(f"   端口: {config.tts.port}")
    print(f"   默认语音: {config.tts.default_voice}")
    print(f"   默认格式: {config.tts.default_format}")
    print(f"   默认语速: {config.tts.default_speed}")
    print(f"   需要API密钥: {config.tts.require_api_key}")
    print("=" * 50)

    # 启动HTTP服务器
    start_http_server()

if __name__ == "__main__":
    main()
