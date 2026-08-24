# sdrtrunk sidecar（W-01）容器验收镜像
#
# 用途：在无本机 JVM 环境 / CI 中运行 sdrtrunk_bridge 完整验收
#   - simulate：合成 P25 WAV → 过桥 → 结构化 JSON（零 JVM 依赖）
#   - live：构建时传 SDRTRUNK_ZIP_URL 内置 sdrtrunk 发行包后可探测/运行
#
# 构建（simulate 验收，默认）：
#   docker build -f mcpserver/rf_brain/sdrtrunk_bridge/Dockerfile -t sdrtrunk-bridge .
# 构建（含 sdrtrunk 发行包，live 探测）：
#   docker build --build-arg SDRTRUNK_ZIP_URL=https://github.com/DSheirer/sdrtrunk/releases/download/<ver>/<zip> \
#                --build-arg JMBE_ZIP_URL=<jmbe-zip> -t sdrtrunk-bridge .
# 运行：
#   docker run --rm -v "$PWD/out:/out" sdrtrunk-bridge
# 或用 docker-compose.yml 一键 build+run。

# 基础镜像：eclipse-temurin 21（sdrtrunk 官方要求 Java 21+）
FROM eclipse-temurin:21-jre-jammy

ARG DEBIAN_FRONTEND=noninteractive
# live 模式依赖：sdrtrunk 发行包 zip 直链（GitHub Releases）+ jmbe 库 zip
ARG SDRTRUNK_ZIP_URL=""
ARG JMBE_ZIP_URL=""

# Python 3（Ubuntu jammy 自带 3.10）+ W-01 验收最小依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

# 可选：sdrtrunk 发行包（live 模式；默认跳过，simulate 验收不需要）
RUN if [ -n "${SDRTRUNK_ZIP_URL}" ]; then \
        curl -fsSL "${SDRTRUNK_ZIP_URL}" -o /tmp/sdrtrunk.zip \
        && mkdir -p /opt/sdrtrunk && unzip -q /tmp/sdrtrunk.zip -d /opt/sdrtrunk \
        && rm /tmp/sdrtrunk.zip; \
    fi

# 可选：jmbe 库（P25-1 IMBE / P25-2、DMR、NXDN AMBE 语音帧）
RUN if [ -n "${JMBE_ZIP_URL}" ]; then \
        curl -fsSL "${JMBE_ZIP_URL}" -o /tmp/jmbe.zip \
        && mkdir -p /opt/jmbe && unzip -q /tmp/jmbe.zip -d /opt/jmbe \
        && rm /tmp/jmbe.zip; \
    fi

ENV PIP_NO_CACHE_DIR=1
# numpy: bridge/schema 依赖；pytest: 跑验收测试；cryptography: 顺带覆盖 mesh 测试
RUN python3 -m pip install "numpy>=2.0" pytest cryptography

WORKDIR /app
# 拷贝 rf_brain 包（含 sdrtrunk_bridge）——accept 脚本经 parents[3] 定位 /app
COPY mcpserver/__init__.py mcpserver/__init__.py
COPY mcpserver/rf_brain/ mcpserver/rf_brain/
COPY mcpserver/rf_brain/sdrtrunk_bridge/docker_entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 默认：simulate 完整验收（单元测试 + 验收脚本）
CMD ["bash", "/app/entrypoint.sh"]
