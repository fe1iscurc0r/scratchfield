# R54 MODEM73 KISS TNC 接入 radio_suite 方案

> 生成：2026-08-31 · 来源：github.com/RFnexus/modem73（2026-08-31 浅克隆源码勘察）
> 目标：把 MODEM73（OFDM/ROBUST/MFSK 软件调制解调器，任意 2400 Hz 电台 + 声卡）接入 radio_suite，为 IC-705 增加数字模式新通道，集成 Hamlib/rigctl PTT。
> 状态：方案 + 桥接脚本（`tools/modem73_kiss_bridge.py`）

---

## 0. 结论速览

MODEM73 是一个「声卡 + KISS over TCP + JSON control port」的软件调制解调器，天然适合作为 radio_suite 的一条数字模式后端：**声卡收 I/Q 音频 → MODEM73 解调出 KISS 帧 → TCP 8001 输出 → 桥接脚本转 APRS/数据上报**。IC-705 用一根 USB 线同时解决音频（内置声卡）与 CAT（rigctl PTT），硬件零改造。

链路形态：

```
IC-705 (USB-D 数据模式, 2400Hz)
   │  USB 音频（内置声卡）       └─ USB CAT（串口 → rigctld）
   ▼                                  ▼
MODEM73 (声卡 I/O, --rigctl localhost:4532)
   │  KISS over TCP :8001            (PTT 经 rigctld 键控)
   ▼
tools/modem73_kiss_bridge.py ──► APRS-IS / 数据上报
   │  JSON control port :8073（状态/配置/选模式）
   ▼
radio_suite（状态面板 / ConfigView）
```

---

## 1. IC-705 音频接线

IC-705 自带 USB 声卡 + USB CAT，**无需外接声卡或数据线**：

| 项 | 配置 |
|---|---|
| 物理连接 | 单根 USB 线（IC-705 的 USB 口 → 主机），同时承载音频与 CAT |
| 声卡设备 | IC-705 在主机上枚举为一个 USB Audio 设备（Linux 下如 `hw:CARD=IC-705` 或 PulseAudio 里的 `IC-705`） |
| 音频入（主机→电台） | MODEM73 输出设备选 IC-705 声卡，送调制音频到电台发射 |
| 音频出（电台→主机） | MODEM73 输入设备选 IC-705 声卡，收电台解调前的基带音频 |
| 电台工作模式 | **USB-D**（数据模式）用于 HF/SSB；VHF/UHF 用 **FM**。MODEM73 的 OFDM 模式在 FM 与 SSB 下都能跑 2400 Hz |
| 电平 | 主机音频输出先调到 IC-705 ALC 不触发为准（约 -6 dBFS），MODEM73 `--tx-level` 从 40~60 起步再调 |

> 注意：IC-705 的 USB 音频与 CAT 是同一根线，Linux 下 CAT 串口通常为 `/dev/ttyACM0`（或 `/dev/ttyUSB0`），音频设备名以 `aplay -l` / `arecord -l` 实测为准。

## 2. rigctl / rigctld PTT 配置

MODEM73 通过 rigctld 键控 IC-705（`rigctl_ptt.hh`：连 `localhost:4532`，发 `T 1`/`T 0`，读 `RPRT 0` 确认）：

```bash
# 1) 起 rigctld（IC-705 的 Hamlib 模型号 3085，串口/波特率按实际改）
rigctld -m 3085 -r /dev/ttyACM0 -s 115200

# 2) 起 MODEM73，PTT 走 rigctl，headless 模式
./modem73 --headless --rigctl localhost:4532

# 3) （可选）直接 HAMLIB PTT：modem73 编译时带 libhamlib-dev，可在 CONFIG 里选 HAMLIB 直连，省掉 rigctld
```

其它 PTT 备选（`kiss_tnc.hh` 枚举）：`NONE`（喇叭对讲）、`VOX`、`COM`（串口 DTR/RTS，如 AIOC 一体线）、`CM108`（USB 声卡 GPIO）。IC-705 首选 **RIGCTL / HAMLIB**。

MODEM73 端口默认值（`kiss_tnc.hh` + `CONTROL_PORT.md`）：

| 端口 | 协议 | 用途 |
|---|---|---|
| 8001 | KISS over TCP | 数据帧进出 |
| 8073 | JSON（4 字节大端长度前缀 + JSON） | 状态/配置/选模式 |

选模式（`README.md`）：OFDM（默认，BPSK~QAM4096、码率 1/4~5/6、790 bps~13 kbps）/ ROBUST（1150~149 bps，HF 衰落路径）/ MFSK（弱信号备份）。接收端三种模式同时解码，无需切模式。

---

## 3. 桥接脚本设计（`tools/modem73_kiss_bridge.py`）

纯标准库，职责单一：

- **KISS 编解码**：`FEND=0xC0, FESC=0xDB, TFEND=0xDC, TFESC=0xDD, CMD_DATA=0x00`（与 `kiss_tnc.hh` 一致）。
- **读 KISS over TCP**：连 `127.0.0.1:8001`，按 FEND 定界切帧，逐帧上报。
- **上报**：把 KISS 数据帧转成 APRS-IS 风格字符串（源站呼 + 目标 + 路径 + 信息）或 JSON 数据上报；`--aprs` 走 APRS-IS passthrough，`--json` 落 JSONL，默认打印。
- **`--simulate` 自测**：不依赖真电台/真 MODEM73——本地起一个假 MODEM73 KISS 服务端，注入若干合成 KISS 帧（模拟 OFDM 解调后的字节流），桥接脚本连上去解出帧并完成上报，证明「声卡解调 → KISS → 上报」链路可跑通。

命令行：

```bash
# 连真 MODEM73，JSON 上报
python tools/modem73_kiss_bridge.py --host 127.0.0.1 --port 8001 --json out.jsonl

# 自测（模拟音频解调 → KISS → 上报，无需任何硬件）
python tools/modem73_kiss_bridge.py --simulate
```

---

## 4. radio_suite 接入点

- **状态面板**：轮询 control port 8073 `get_status`（`last_snr/last_ber/ber_ema/rx_frame_count/population`），把 MODEM73 链路质量并入 radio_suite 现有频谱/链路状态视图。
- **ConfigView**：`set_config` 切 `modem_type`/`modulation`/`code_rate`，对应 radio_suite 的数字模式下拉。
- **数据上报**：桥接脚本输出统一为 radio_suite 的 APRS/数据上报格式，与现有 `aprs_igate` 汇合。

## 5. 验收对照

- ✅ 方案含 IC-705 音频接线（§1）与 rigctl 配置（§2）。
- ✅ 桥接脚本可跑通模拟音频（`--simulate` 自测，见 `tools/modem73_kiss_bridge.py` + `tools/test_modem73_kiss_bridge.py`）。

## 6. 风险与待办

- IC-705 声卡/CAT 设备名在不同 OS/驱动下不同，落地按 `aplay -l`/`ls /dev/ttyACM*` 实测。
- MODEM73 Windows 版为独立 fork（Win32 + PDCurses），串口 PTT 不稳，建议上游版跑 WSL。
- 真机联调需校准 `--tx-level` 与 IC-705 ALC，避免过驱动。
