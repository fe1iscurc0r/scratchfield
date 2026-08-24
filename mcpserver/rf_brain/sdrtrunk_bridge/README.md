# sdrtrunk sidecar（W-01）· rf_brain P6 多协议解码桥

rf_brain 已有 Phase6 多协议解码库（aprs/psk31/dtmf/pocsag，纯 numpy），
但 P25/DMR 商业制式需 sdrtrunk（JVM）。本模块是 **JVM 独立进程桥**：
sdrtrunk 解码结果 → 结构化 JSON → mcpserver 工具总线。

## 架构

```
┌────────────┐   WAV 音频    ┌──────────────────────────────┐
│ 音频文件/SDR │ ──────────→ │ sdrtrunk（JVM 独立进程）        │
└────────────┘              │  · P25P1/P25P2/DMR/NXDN 解码    │
                            │  · IMBE/AMBE 语音帧（jmbe 库）   │
                            └──────────────┬───────────────┘
                                           │ NDJSON（stdout）
                                           ▼
                            ┌──────────────────────────────┐
                            │ SdrtrunkBridge（本模块）       │
                            │  · schema.py  统一 JSON schema │
                            │  · bridge.py  子进程/stdout 桥 │
                            │  · adapter.py 注册进 Phase6    │
                            └──────────────┬───────────────┘
                                           │ SdrtrunkEvent（协议无关）
                                           ▼
                            ┌──────────────────────────────┐
                            │ mcpserver 工具总线 / 决策层     │
                            └──────────────────────────────┘
```

## 模块

| 文件 | 职责 |
|---|---|
| `schema.py` | 统一事件 JSON schema（协议无关顶层字段 + payload 协议细节） |
| `bridge.py` | `SdrtrunkBridge`：live（真实 JVM 子进程）/ simulate（内置模拟器）两种模式 |
| `adapter.py` | `register_sdrtrunk_decoder()` 显式注册进 Phase6 注册表（默认不注册） |
| `accept_sdrtrunk_bridge.py` | 验收脚本：模拟音频 → 过桥 → 结构化 JSON → grep 断言 |
| `test_sdrtrunk_bridge.py` | 10 项验收测试 |

## 统一 JSON schema（顶层字段）

```json
{
  "schema": "sdrtrunk-event",
  "version": "1.0",
  "source": "sdrtrunk",
  "ts": "2026-08-23T00:00:00Z",
  "protocol": "P25P1",
  "event_type": "call_start",
  "frequency_hz": 855000000,
  "talkgroup": 12345,
  "from_radio": 67890,
  "to_alias": null,
  "details": "...",
  "payload": { "nac": 659, "modulation": "C4FM", "frame_count": 30 }
}
```

必填字段（`REQUIRED_FIELDS`，验收 grep/assert 目标）：
`schema, version, source, ts, protocol, event_type, frequency_hz, talkgroup,
from_radio, to_alias, details, payload`。

## 使用

```python
from mcpserver.rf_brain.sdrtrunk_bridge import SdrtrunkBridge

# 模拟模式（无 JVM 环境验收用）
events = SdrtrunkBridge(mode="simulate", audio_path="call.wav").decode_all()

# live 模式（真机/云服）
events = SdrtrunkBridge(
    mode="live", java_bin="java",
    sdrtrunk_jar="/opt/sdrtrunk/sdr-trunk.jar",
).decode_all()

# 接入 Phase6 解码链（可选）
from mcpserver.rf_brain.sdrtrunk_bridge.adapter import register_sdrtrunk_decoder
register_sdrtrunk_decoder()
from mcpserver.rf_brain.decoders import decode_all
results = decode_all(iq, 48000.0, audio_path="call.wav")
```

## 验收

```bash
# 验收脚本（模拟音频文件过桥 → P25P1 帧 → 结构化 JSON）
python mcpserver/rf_brain/sdrtrunk_bridge/accept_sdrtrunk_bridge.py

# 单元测试
python -m pytest mcpserver/rf_brain/test_sdrtrunk_bridge.py -q
```

## JVM 依赖（云服/真机运行前提）

| 项 | 说明 |
|---|---|
| Java | **21+**（sdrtrunk 官方要求；本机 OpenJDK 17 仅够跑 simulate/测试） |
| sdrtrunk | 从 https://github.com/DSheirer/sdrtrunk/releases 下载发行包（内含 JRE，也可用系统 JDK） |
| jmbe 库 | P25-1（IMBE）/ P25-2、DMR、NXDN（AMBE）语音帧需 jmbe jar，缺失时 sdrtrunk 仅解信令不吐语音 |
| live 模式 | `java -jar <sdrtrunk>.jar` 由桥启动；sdrtrunk 侧需配置好播放列表/信道 |
| simulate 模式 | 零 JVM 依赖，CI/无 JVM 环境验收桥链路用 |

**硬约束遵守**：本模块不触碰 NEKO/apiserver 主流程；adapter 默认不注册，
调用方显式 `register_sdrtrunk_decoder()` 才接入，既有 Phase6 四解码器集合不变。

## 阻塞说明（如实记录）

- 本机已装 OpenJDK 17，但**未安装 sdrtrunk 发行包**，也没有真实 P25/DMR
  录音文件 → live 真机过桥无法在本机实测。验收按工单动作 3「模拟音频文件
  过桥验证」执行（simulate 模式，P25P1 帧 → 结构化 JSON，字段完整断言通过）。
  真机过桥需云服/真机部署 JVM 21 + sdrtrunk 后运行 live 模式。
