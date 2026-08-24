# RS-BA1 V2 INI 配置文件完整电台型号地址表

> 本文档由解析 RS-BA1 V2 全部 INI 配置文件自动生成。
> INI 目录: `d:\my git\RS-BA1\RemoteController\models`
> RemoteUtility: `d:\my git\RemoteUtility\models.ini` / `d:\my git\RemoteUtility\RadioSch.ini`

## 目录

1. [RemoteUtility models.ini 型号映射总表](#1-remoteutility-modelsini-型号映射总表)
2. [RemoteController 电台型号 INI 地址表](#2-remotecontroller-电台型号-ini-地址表)
3. [general_single / general_dual / general_split 区别说明](#3-generalsingle--generaldual--generalsplit-区别说明)
4. [RadioSch.ini 调度配置说明](#4-radioschini-调度配置说明)
5. [各电台频率范围 / 发射频段明细](#5-各电台频率范围--发射频段明细)
6. [CI-V 模式代码表](#6-ci-v-模式代码表)
7. [波特率代码映射表](#7-波特率代码映射表)
8. [IC-705.ini 特别说明](#8-ic-705ini-特别说明)

---

## 1. RemoteUtility models.ini 型号映射总表

`models.ini` 是 RemoteUtility (RemoteUty.exe) 维护的型号映射总表，共 **21** 条记录。
该表是 RS-BA1 在 USB/LAN 连接设置里识别电台型号的权威来源。`TYPE=0` 为收发信机，`TYPE=1` 为接收机。

| # | 型号 | CI-V 地址 (HEX) | 波特率 | TYPE | 备注 |
|---|------|----------------|--------|------|------|
| 1 | IC-7000 | 0x70 | 19200 | 0 | 收发信机 |
| 2 | IC-705 | 0xA4 | 115200 | 0 | 收发信机 |
| 3 | IC-7100 | 0x88 | 19200 | 0 | 收发信机 |
| 4 | IC-7200 | 0x76 | 19200 | 0 | 收发信机 |
| 5 | IC-7300 | 0x94 | 115200 | 0 | 收发信机 |
| 6 | IC-7400 | 0x66 | 19200 | 0 | 收发信机 |
| 7 | IC-7410 | 0x80 | 19200 | 0 | 收发信机 |
| 8 | IC-746 | 0x56 | 19200 | 0 | 收发信机 |
| 9 | IC-746PRO | 0x66 | 19200 | 0 | 收发信机 |
| 10 | IC-756PRO | 0x5C | 19200 | 0 | 收发信机 |
| 11 | IC-756PRO2 | 0x64 | 19200 | 0 | 收发信机 |
| 12 | IC-756PRO3 | 0x6E | 19200 | 0 | 收发信机 |
| 13 | IC-7600 | 0x7A | 19200 | 0 | 收发信机 |
| 14 | IC-7610 | 0x98 | 115200 | 0 | 收发信机 |
| 15 | IC-7700 | 0x74 | 19200 | 0 | 收发信机 |
| 16 | IC-7800 | 0x6A | 19200 | 0 | 收发信机 |
| 17 | IC-7850 | 0x8E | 115200 | 0 | 收发信机 |
| 18 | IC-7851 | 0x8E | 115200 | 0 | 收发信机 |
| 19 | IC-9100 | 0x7C | 19200 | 0 | 收发信机 |
| 20 | IC-9700 | 0xA2 | 115200 | 0 | 收发信机 |
| 21 | IC-R8600 | 0x96 | 115200 | 1 | 接收机 |

**说明：**
- `IC-746PRO` 与 `IC-7400` 共用 CI-V 地址 `0x66`（746PRO 是 7400 的海外/前代型号）。
- `IC-7851` 与 `IC-7850` 共用 CI-V 地址 `0x8E`（7851 是 7850 的美规/升级型号）。
- `IC-R8600` 为 `TYPE=1` 接收机，在 RemoteController/models 目录下没有专用 INI，由 `general_*.ini` 兜底。
- `IC-705`、`IC-7300`、`IC-7610`、`IC-7850/7851`、`IC-9700`、`IC-R8600` 均使用 **115200** 波特率；
  其余型号使用 19200 波特率。

---

## 2. RemoteController 电台型号 INI 地址表

下表汇总 `RemoteController/models/` 目录下所有 `IC-*.ini` 的 `[COM]`/`[TYPE]`/`[FREQUENCY]`/`[SETTING]` 关键字段。

| INI 文件 | 型号 | CI-V 地址 | 波特率(代码) | TYPE | 频率范围 (Hz) | 模式列表 |
|----------|------|-----------|-------------|------|---------------|----------|
| IC-7000.ini | IC-7000 | 0x70 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–199999999; 400000000–470000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 6=WFM, 7=CW-R, 8=RTTY-R |
| IC-705.ini | IC-705 | 0xA4 | 7 (115200) | 2=Split | 30000–199999999; 400000000–470000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 6=WFM, 7=CW-R, 8=RTTY-R, 17=DD |
| IC-7100.ini | IC-7100 (Ver1.10 - ) | 0x88 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–199999999; 400000000–470000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD |
| IC-7200.ini | IC-7200 | 0x76 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 7=CW-R, 8=RTTY-R |
| IC-7300.ini | IC-7300 (Ver1.20 - ) | 0x94 | 2,3,4,5,6,7 (4800, 9600, 19200, 38400, 57600, 115200) | 2=Split | 30000–74800000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-7400.ini | IC-7400/746PRO | 0x66 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000; 108000000–174000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-7410.ini | IC-7410 | 0x80 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-746.ini | IC-746 | 0x56 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000; 108000000–174000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-756PRO.ini | IC-756PRO | 0x5C | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-756PRO2.ini | IC-756PRO2 | 0x64 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-756PRO3.ini | IC-756PRO3 | 0x6E | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R |
| IC-7600.ini | IC-7600 (Ver2.00 - ) | 0x7A | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7610.ini | IC-7610 (Ver1.10 - ) | 0x98 | 2,3,4,5,6,7 (4800, 9600, 19200, 38400, 57600, 115200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7610_d.ini | IC-7610 (Ver1.10 - ) (DUAL) | 0x98 | 2,3,4,5,6,7 (4800, 9600, 19200, 38400, 57600, 115200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7700.ini | IC-7700 (Ver2.10 - ) | 0x74 | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7800.ini | IC-7800 (Ver3.10 - ) | 0x6A | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7850.ini | IC-7850/7851 (Ver1.30 - ) | 0x8E | 0,1,2,3,4,5,6,7 (300, 1200, 4800, 9600, 19200, 38400, 57600, 115200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-7850_d.ini | IC-7850/7851 (Ver1.30 - ) (DUAL) | 0x8E | 0,1,2,3,4,5,6,7 (300, 1200, 4800, 9600, 19200, 38400, 57600, 115200) | 1=Dual | 30000–60000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R |
| IC-9100.ini | IC-9100 | 0x7C | 0,1,2,3,4 (300, 1200, 4800, 9600, 19200) | 2=Split | 30000–60000000; 108000000–174000000; 420000000–480000000; 1240000000–1320000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD |
| IC-9700.ini | IC-9700 | 0xA2 | 2,3,4,5,6,7 (4800, 9600, 19200, 38400, 57600, 115200) | 2=Split | 144000000–148000000; 430000000–450000000; 1240000000–1300000000 | 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD |

> `IC-7610_d.ini` / `IC-7850_d.ini` 是 Dual VFO 变体（`TYPE=1`），分别对应 IC-7610 / IC-7850 的双接收模式。

---

## 3. general_single / general_dual / general_split 区别说明

`general_*.ini` 是 RS-BA1 的通用兜底定义文件，用于未被专用 INI 覆盖的 Icom 电台（含 IC-R8600）。
三者的核心区别在 `[TYPE] TYPE` 字段以及由此启用的 VFO/收发命令集合：

| 文件 | TYPE | 含义 | CIV2(Split) | Exe_Vfoa/Vfob | Exe_Abeq/Ab/Mseq | Exe_Dualoff/On | INITIAL CMD2 |
|------|------|------|-------------|---------------|------------------|----------------|--------------|
| general_single.ini | 0 | Single | 0 | 0/0 | 0/0/0 | 0/0 | 164600 |
| general_dual.ini | 1 | Dual | 1 | 1/1 | 1/1/1 | 1/1 | 07C0 |
| general_split.ini | 2 | Split | 1 | 1/1 | 1/1/0 | 0/0 | 164600 |

**详细差异：**

- **general_single.ini (`TYPE=0`, Single)**
  - 单 VFO 模式，最简命令集。`CIV2(Split)=0`、`Exe_Vfoa/Vfob=0`、`Exe_Abeq/Ab/Mseq=0`。
  - `[INITIAL] CMD2 = 164600`（仅设置 VFO），不发送双 watch / Satellite 命令。
  - 适用于：单接收老型号电台、IC-R8600 等接收机。

- **general_dual.ini (`TYPE=1`, Dual)**
  - 双 VFO / 双接收模式。`CIV2(Split)=1`、`Exe_Vfoa/Vfob=1`、`Exe_Abeq/Ab/Mseq=1`。
  - 显式带双 watch 切换命令：`Exe_Dualoff CMD217=07C0`、`Exe_Dualon CMD218=07C1`、
    `Exe_Macc CMD220=07D0`、`Exe_Sacc CMD221=07D1`、`Exe_Acc CMD219=07D2`。
  - `[INITIAL] CMD2 = 07C0`（开机即关闭双 watch，避免冲突）。
  - 适用于：IC-7610_d / IC-7850_d 等双接收变体。

- **general_split.ini (`TYPE=2`, Split)**
  - 异频 (Split) 模式。`CIV2(Split)=1`、`Exe_Vfoa/Vfob=1`、`Exe_Abeq/Ab=1`。
  - **不**带双 watch 命令（`Exe_Mseq=0`、`Exe_Dualoff/On=0`、`Exe_Acc/Macc/Sacc=0`）。
  - `[INITIAL] CMD2 = 164600`（仅设 VFO，不强制双 watch 状态）。
  - 适用于：仅做收发异频、不需要双接收的电台。

**三者共同的兜底字段：** `ADR` 为空（运行时由 models.ini 注入），`BAUD=0,1,2,3,4`（允许 300/1200/4800/9600/19200 老式五档全可选），
`MODE = 0,1,2,3,4,5,7,8,12,13,17`（覆盖 LSB/USB/AM/CW/RTTY/FM/CW-R/RTTY-R/PSK/PSK-R/DD），
`FREQUENCY RANGE0 = 5000 – 3335000000`（极宽兜底范围），`[TX BAND]` 全部为空（发射能力由具体电台决定）。

---

## 4. RadioSch.ini 调度配置说明

`RadioSch.ini` 是 RemoteUtility 用来识别 Icom 原厂 USB 驱动线缆（HUB/Audio/COM 三合一）的 VID/PID 调度表。
`[MAIN] CNT=4` 表示定义了 4 组线缆 VID/PID 组合。匹配到任一组即自动加载虚拟声卡 + 虚拟串口驱动。

`RadioSch.dll` 在运行时读取此 INI，枚举系统 USB 设备，按 HUB→AUDIO→COM 三级 VID/PID 比对识别线缆型号。

| 组号 | HUB (VID/PID) | AUDIO (VID/PID) | COM (VID/PID) | 备注 |
|------|---------------|-----------------|---------------|------|
| VIDPID1 | VID_0424&PID_2502 | VID_08BB&PID_2901 | VID_10C4&PID_EA60 |  |
| VIDPID2 | VID_0451&PID_2046 | VID_08BB&PID_2901 | VID_10C4&PID_EA60 |  |
| VIDPID3 | VID_0424&PID_2513 | VID_08BB&PID_2901 | VID_10C4&PID_EA60 |  |
| VIDPID4 | VID_0451&PID_2046 | VID_08BB&PID_2901 | VID_0C26&PID_0036 | ID=A |

**VID/PID 厂商解读：**
- `VID_0424` = Microchip (原 SMSC) USB Hub 控制器；`VID_0451` = Texas Instruments USB Hub。
- `VID_08BB` = Texas Instruments PCM2901 USB Audio CODEC（线缆内的 USB 声卡）。
- `VID_10C4` = Silicon Labs CP210x USB-to-UART（线缆内的 USB 转串口）；
  `VID_0C26` = ICOM 自家 OEM 串口芯片（仅 VIDPID4，带 `ID=A` 标记，可能是特殊固件版本）。

---

## 5. 各电台频率范围 / 发射频段明细

以下逐型号列出 `[FREQUENCY]`（接收范围）、`[TX BAND]`（发射范围，单位 Hz）及关键 `[SETTING]` 字段。

### IC-7000  (`IC-7000.ini`)

- **CI-V 地址:** `0x70`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 6=WFM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1 | **ANT:** 0 | **ATT:** 0,12 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 199999999 Hz (200 MHz)
  - RANGE: 400000000 Hz (400 MHz) – 470000000 Hz (470 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=1, BSR1200=0

### IC-705  (`IC-705.ini`)

- **CI-V 地址:** `0xA4`
- **波特率:** 7 → 115200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 6=WFM, 7=CW-R, 8=RTTY-R, 17=DD
- **PRE:** 0,1,2 | **ANT:** 0 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3,6,7,8,9 | **DSQL:** 0,1,2 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 199999999 Hz (200 MHz)
  - RANGE: 400000000 Hz (400 MHz) – 470000000 Hz (470 MHz)
- **[TX BAND] 发射范围:**
  - RANGE: 30000 Hz (30 kHz) – 29999999 Hz (30 MHz)
  - RANGE: 30000000 Hz (30 MHz) – 59999999 Hz (60 MHz)
  - RANGE: 60000000 Hz (60 MHz) – 74799999 Hz (74.8 MHz)
  - RANGE: 74800000 Hz (74.8 MHz) – 199999999 Hz (200 MHz)
  - RANGE: 400000000 Hz (400 MHz) – 470000000 Hz (470 MHz)
- **[SCOPE]:** TYPE=1, CONNECT=0,1
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=1, BSR1200=0

### IC-7100 (Ver1.10 - )  (`IC-7100.ini`)

- **CI-V 地址:** `0x88`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD
- **PRE:** 0,1,2 | **ANT:** 0 | **ATT:** 0,12 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3 | **DSQL:** 0,1,2 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 199999999 Hz (200 MHz)
  - RANGE: 400000000 Hz (400 MHz) – 470000000 Hz (470 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=1, BSR1200=0

### IC-7200  (`IC-7200.ini`)

- **CI-V 地址:** `0x76`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1 | **ANT:** 0 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0 | **DSQL:** 0 | **RISE_TIME:** 
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7300 (Ver1.20 - )  (`IC-7300.ini`)

- **CI-V 地址:** `0x94`
- **波特率:** 2,3,4,5,6,7 → 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 74800000 Hz (74.8 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[SCOPE]:** TYPE=1
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7400/746PRO  (`IC-7400.ini`)

- **CI-V 地址:** `0x66`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
  - RANGE: 108000000 Hz (108 MHz) – 174000000 Hz (174 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=0, BSR1200=0

### IC-7410  (`IC-7410.ini`)

- **CI-V 地址:** `0x80`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-746  (`IC-746.ini`)

- **CI-V 地址:** `0x56`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1 | **ATT:** 0,20 | **FIL:** 1,2 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
  - RANGE: 108000000 Hz (108 MHz) – 174000000 Hz (174 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=0, BSR1200=0

### IC-756PRO  (`IC-756PRO.ini`)

- **CI-V 地址:** `0x5C`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,6,12,18 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-756PRO2  (`IC-756PRO2.ini`)

- **CI-V 地址:** `0x64`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,6,12,18 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-756PRO3  (`IC-756PRO3.ini`)

- **CI-V 地址:** `0x6E`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,6,12,18 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7600 (Ver2.00 - )  (`IC-7600.ini`)

- **CI-V 地址:** `0x7A`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=2; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,6,12,18 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3,4
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7610 (Ver1.10 - )  (`IC-7610.ini`)

- **CI-V 地址:** `0x98`
- **波特率:** 2,3,4,5,6,7 → 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=3; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[SCOPE]:** TYPE=2, CONNECT=2
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7610 (Ver1.10 - ) (DUAL)  (`IC-7610_d.ini`)

- **CI-V 地址:** `0x98`
- **波特率:** 2,3,4,5,6,7 → 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 1 = Dual; DUAL=1; DUAL_KIND=3; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,4,5 | **ATT:** 0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[SCOPE]:** TYPE=2, CONNECT=2
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7700 (Ver2.10 - )  (`IC-7700.ini`)

- **CI-V 地址:** `0x74`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,2,3,4,5,6 | **ATT:** 0,6,12,18 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7800 (Ver3.10 - )  (`IC-7800.ini`)

- **CI-V 地址:** `0x6A`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=1; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,2,3,4,5,6 | **ATT:** 0,3,6,9,12,15,18,21 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7850/7851 (Ver1.30 - )  (`IC-7850.ini`)

- **CI-V 地址:** `0x8E`
- **波特率:** 0,1,2,3,4,5,6,7 → 300, 1200, 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 1 = Dual; DUAL=0; DUAL_KIND=1; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,2,3,4,5,6 | **ATT:** 0,3,6,9,12,15,18,21 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:**
  - RANGE: 30000 Hz (30 kHz) – 1999999 Hz (2 MHz)
  - RANGE: 2000000 Hz (2 MHz) – 3999999 Hz (4 MHz)
  - RANGE: 4000000 Hz (4 MHz) – 5999999 Hz (6 MHz)
  - RANGE: 6000000 Hz (6 MHz) – 7999999 Hz (8 MHz)
  - RANGE: 8000000 Hz (8 MHz) – 10999999 Hz (11 MHz)
  - RANGE: 11000000 Hz (11 MHz) – 14999999 Hz (15 MHz)
  - RANGE: 15000000 Hz (15 MHz) – 19999999 Hz (20 MHz)
  - RANGE: 20000000 Hz (20 MHz) – 21999999 Hz (22 MHz)
  - RANGE: 22000000 Hz (22 MHz) – 25999999 Hz (26 MHz)
  - RANGE: 26000000 Hz (26 MHz) – 29999999 Hz (30 MHz)
  - RANGE: 30000000 Hz (30 MHz) – 60000000 Hz (60 MHz)
- **[SCOPE]:** TYPE=0, CONNECT=2
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-7850/7851 (Ver1.30 - ) (DUAL)  (`IC-7850_d.ini`)

- **CI-V 地址:** `0x8E`
- **波特率:** 0,1,2,3,4,5,6,7 → 300, 1200, 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 1 = Dual; DUAL=1; DUAL_KIND=1; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 12=PSK, 13=PSK-R
- **PRE:** 0,1,2 | **ANT:** 0,1,2,3,4,5,6 | **ATT:** 0,3,6,9,12,15,18,21 | **FIL:** 1,2,3 | **TONE:** 0,1,2 | **DSQL:** 0 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
- **[TX BAND] 发射范围:**
  - RANGE: 30000 Hz (30 kHz) – 1999999 Hz (2 MHz)
  - RANGE: 2000000 Hz (2 MHz) – 3999999 Hz (4 MHz)
  - RANGE: 4000000 Hz (4 MHz) – 5999999 Hz (6 MHz)
  - RANGE: 6000000 Hz (6 MHz) – 7999999 Hz (8 MHz)
  - RANGE: 8000000 Hz (8 MHz) – 10999999 Hz (11 MHz)
  - RANGE: 11000000 Hz (11 MHz) – 14999999 Hz (15 MHz)
  - RANGE: 15000000 Hz (15 MHz) – 19999999 Hz (20 MHz)
  - RANGE: 20000000 Hz (20 MHz) – 21999999 Hz (22 MHz)
  - RANGE: 22000000 Hz (22 MHz) – 25999999 Hz (26 MHz)
  - RANGE: 26000000 Hz (26 MHz) – 29999999 Hz (30 MHz)
  - RANGE: 30000000 Hz (30 MHz) – 60000000 Hz (60 MHz)
- **[SCOPE]:** TYPE=0, CONNECT=2
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=1, BSR144=0, BSR430=0, BSR1200=0

### IC-9100  (`IC-9100.ini`)

- **CI-V 地址:** `0x7C`
- **波特率:** 0,1,2,3,4 → 300, 1200, 4800, 9600, 19200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=0
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD
- **PRE:** 0,1,2 | **ANT:** 0,1 | **ATT:** 0,20 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3 | **DSQL:** 0,1,2 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 30000 Hz (30 kHz) – 60000000 Hz (60 MHz)
  - RANGE: 108000000 Hz (108 MHz) – 174000000 Hz (174 MHz)
  - RANGE: 420000000 Hz (420 MHz) – 480000000 Hz (480 MHz)
  - RANGE: 1240000000 Hz (1240 MHz) – 1320000000 Hz (1320 MHz)
- **[TX BAND] 发射范围:** — （general 兜底或接收机无发射）
- **[TRANSPWR]:** CONTROL=0
- **[UI] BSR:** BSRHF50=1, BSR144=1, BSR430=1, BSR1200=1

### IC-9700  (`IC-9700.ini`)

- **CI-V 地址:** `0xA2`
- **波特率:** 2,3,4,5,6,7 → 4800, 9600, 19200, 38400, 57600, 115200
- **TYPE:** 2 = Split; DUAL=0; DUAL_KIND=0; VER17=1
- **模式 (MODE):** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 7=CW-R, 8=RTTY-R, 17=DD
- **PRE:** 0,1 | **ANT:** 0 | **ATT:** 0,10 | **FIL:** 1,2,3 | **TONE:** 0,1,2,3,6,7,8,9 | **DSQL:** 0,1,2 | **RISE_TIME:** 0,1,2,3
- **[FREQUENCY] 接收范围:**
  - RANGE: 144000000 Hz (144 MHz) – 148000000 Hz (148 MHz)
  - RANGE: 430000000 Hz (430 MHz) – 450000000 Hz (450 MHz)
  - RANGE: 1240000000 Hz (1240 MHz) – 1300000000 Hz (1300 MHz)
- **[TX BAND] 发射范围:**
  - RANGE: 144000000 Hz (144 MHz) – 148000000 Hz (148 MHz)
  - RANGE: 430000000 Hz (430 MHz) – 450000000 Hz (450 MHz)
  - RANGE: 1240000000 Hz (1240 MHz) – 1300000000 Hz (1300 MHz)
- **[SCOPE]:** TYPE=1, CONNECT=2
- **[TRANSPWR]:** CONTROL=1, CMD_ON=1801, CMD_OFF=1800
- **[UI] BSR:** BSRHF50=0, BSR144=1, BSR430=1, BSR1200=1

---

## 6. CI-V 模式代码表

`[SETTING] MODE` 字段使用 CI-V 模式代码（对应 Icom CI-V 命令 `0x06` 子命令）：

| 代码 | 模式 | 代码 | 模式 |
|------|------|------|------|
| 0 | LSB | 6 | WFM |
| 1 | USB | 7 | CW-R |
| 2 | AM | 8 | RTTY-R |
| 3 | CW | 12 | PSK |
| 4 | RTTY | 13 | PSK-R |
| 5 | FM | 17 | DD |

---

## 7. 波特率代码映射表

`[COM] BAUD` 字段在电台 INI 里是代码（可多选，逗号分隔）；在 `models.ini` 里直接是数值波特率。

| 代码 | 波特率 (bps) | 说明 |
|------|-------------|------|
| 0 | 300 | 低速（老型号） |
| 1 | 1200 |  |
| 2 | 4800 |  |
| 3 | 9600 |  |
| 4 | 19200 | 老型号默认（19200） |
| 5 | 38400 |  |
| 6 | 57600 |  |
| 7 | 115200 | 新型号默认（115200）；IC-705 仅支持此档 |

> 注意：`general_*.ini` 的 `BAUD=0,1,2,3,4` 表示老式 5 档（300–19200）全可选；
> 新型号（IC-7300/7610/9700/7850）的 `BAUD=2,3,4,5,6,7` 表示 4800–115200 全可选；
> IC-705 的 `BAUD=7` 表示仅 115200 一档。`models.ini` 中给出的是各型号的默认波特率。

---

## 8. IC-705.ini 特别说明

- **CI-V 地址:** `0xA4` （0xA4，与 models.ini 一致，IC-705 专用）
- **波特率:** 代码 `7` → 115200 bps（与 models.ini 的 `BAUD=115200` 一致）
- **TYPE:** 2 = Split（Split 模式，IC-705 原生支持异频）
- **VER17:** 1 （V1.7 新增型号标记，启用 WLAN/USB 直连与 SD 记录等扩展命令）
- **模式列表:** 0=LSB, 1=USB, 2=AM, 3=CW, 4=RTTY, 5=FM, 6=WFM, 7=CW-R, 8=RTTY-R, 17=DD
- **连接方式:** `[CONNECT] CON0=1,0,3,USB` / `CON1=3,0,2,WLAN` —— 同时支持 USB 与 WLAN 两种直连。
- **接收频率范围:** 30 kHz – 470 MHz（HF/VHF/UHF 全段，分两段：0.03–199.999999 MHz + 400–470 MHz）。
- **发射频段:** 5 段 —— HF(30k–30M)、50M、60M(仅美规 6–7.48M)、VHF(74.8M–200M)、UHF(400–470M)。
- **发射功率:** DC 13.8V: 0.5/1/2.5/5/10 W；电池: 0.5/1/2.5/5 W。
- **特色扩展命令（非通用 INI 没有的）:**
  - `CMD70=1A0B` (MaxTxPower)、`CMD71=1A050036` (Battery)、`CMD72=1A050037` (DC)
  - `CMD29=1A04` (AGC)、`CMD33=1A050359` (Vox dly)、`CMD34=1A050360` (Vox vc dly)
  - `CMD47=1658` (SSB TX BW)、`CMD51=1A03` (FilW)、`CMD53=1656` (Slope)、`CMD57=1657` (MnotchW)
  - `CMD120=1A050110`/`CMD121=1A050111` (USB AF/SQL)、`CMD123=1A050115` (WLAN SQL)
  - `CMD124=1A050252` (CW ratio)、`CMD125=1A050253` (CW rise time)、`CMD126=1A050070` (CW rev)
  - 完整 Scope 频谱命令集（CIV182–CIV197），含 17 段 SCOPE RANGE 覆盖 HF/VHF/UHF。
- **[SCOPE] TYPE=1, GRID=8, EDGE=3**, span 8 档（2.5k–500k）；**[TRANSPWR] CONTROL=1** 支持外置功放控制 (CMD_ON=1801/CMD_OFF=1800)。

---

## 附录：INI 文件结构总览

每个电台 INI 由以下 section 组成（general_*.ini 与专用 INI 结构一致）：

| Section | 用途 |
|---------|------|
| `[DESCRIPTION]` | 文件描述与型号名 (`MODEL`) |
| `[SUPPORT]` | 版本支持标记 (`VER17`=1 表示 V1.7 新增型号) |
| `[TYPE]` | 电台类型 (`TYPE`: 0=Single 1=Dual 2=Split; `DUAL`/`DUAL_KIND`) |
| `[COM]` | CI-V 通信参数 (`ADR` 地址, `BAUD` 波特率代码) |
| `[CONNECT]` | 连接方式表 (`CON0..CON5`: 串口/USB/LAN/WLAN; `INITIAL` 自动连接标志) |
| `[COMMAND]` | CI-V 命令使能位 + 命令码 (`CIV0..CIV222`/`CMD0..CMD222`) |
| `[INITIAL]` | 开机初始化命令序列 (`CMD0..CMD19`) |
| `[UI]` | UI 显示开关 (`BSRHF50/144/430/1200` 频段扫描按钮) |
| `[SETTING]` | 可设选项枚举 (`MODE/PRE/ANT/ATT/FIL/TONE/DSQL/RISE_TIME`) |
| `[METER]` | 表头刻度 (S/PO/ALC/SWR/COMP/RFG/PO_TYPE/SWR_TYPE) |
| `[SQLVR]` | SQL 电压-代码映射 (CI-V↔VR) |
| `[BAND GROUP]` | 频段分组总范围 |
| `[FREQUENCY]` | 接收频率范围 (多 RANGE) |
| `[ANT BAND]` | 天线频段切换点 |
| `[TX BAND]` | 发射频段范围 (多 RANGE) |
| `[DUP OFFSET]` | 差频最大值 (`MAX`) |
| `[NB]` | 噪声抑制频段 (`BAND`) |
| `[FILTER]` | FM/AM/SLOPE 滤波器参数 |
| `[BW]` | 各模式带宽范围 (SSB/CW/PSK/RTTY/AM) |
| `[PBT]` | 通带调谐参数 |
| `[MOD_OFF]`/`[MOD]` | 调制源选择 (MIC/ACC/USB/WLAN) |
| `[RX IO]` | 接收 IO 选项 |
| `[AGC]` | AGC 速度选项 (FAST/MID/SLOW) |
| `[ROOF]` | Roofing filter 选项 |
| `[TBW]` | TX 带宽 (LOW/HIGH cutoff) |
| `[CW]` | CW 速度类型 |
| `[VR]` | 各功能 VR 类型 (APF/NRL/PBT/CWP/COMP/BKIND/AGC/DSEL) |
| `[VALID_RANGE]` | Roofing filter 有效范围 |
| `[DSEL_RANGE]` | D-SEL 范围 |
| `[TX_POWER]` | 发射功率档位 (`DISP/MAX/POWER0/POWER1`) |
| `[TRANSPWR]` | 外置功放控制 (`CONTROL/CONNECT/CMD_ON/CMD_OFF/ADDPREAMBLE/WAIT_OFF`) |
| `[SCOPE]` | 频谱功能参数 (`CONNECT/TYPE/GRID/SPAN/EDGE/RANGE0..19/REFLV/WAVELV`) |
| `[CONNECTOR]` | ACC/USB 连接器配置 (`ACCUSB`) |

> 文档生成自实际 INI 文件解析，非官方手册；CI-V 地址/波特率以 `models.ini` 为权威，
> 频率/模式/命令以各 `RemoteController/models/IC-*.ini` 为权威。
