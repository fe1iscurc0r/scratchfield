# 边缘频谱哨兵 · 433MHz 传感器协议勘察报告（N-01）

> 批次：SPEC-12 第七批 · 智能体 N
> 范围：Phase 1 只做 433MHz OOK、单载波、短帧（<200bit）传感器协议，SX1278 OOK 模式可收
> 硬约束：协议格式是公开事实，本文只引格式事实，不复制 rtl_433（GPL-2.0）代码；独立实现时标注来源

---

## 0. 结论摘要（先给结论）

选定 3 个协议作为 Phase 1 落地目标，覆盖「温湿度站 / 简单温湿度 / 门磁·PIR 安防」三类哨兵场景：

| 选型 | 协议 | 调制/编码 | 帧长 | 校验 | 落地理由 |
|------|------|-----------|------|------|----------|
| ★ | Acurite 592TXR/Tower | OOK-PWM | 56 bit | 8bit 加和校验 + 偶校验位 | 校验完整、字段丰富、社区文档最全 |
| ★ | Nexus TH（TFA 30.3209 等） | OOK-PPM | 36 bit | 无校验（固定 nibble+12 重复帧） | 编码最简单，PPM 抗噪好，独立实现最干净 |
| ★ | Kerui/EV1527 门磁·PIR | OOK-PWM（x1527） | 24 bit | 无校验（重复 25 帧） | 安防门磁/人体红外，哨兵核心用例 |

备选（本阶段不做，保留在候选表）：Fine Offset WH2、LaCrosse TX141TH-Bv2、Oregon Scientific v1、WT450。

---

## 1. 候选对照表（≥5 行）

| 候选 | 频率 | 调制 | 帧长 | 编码 | 校验 | 灵敏度适配 | 公开文档来源 |
|------|------|------|------|------|------|-----------|--------------|
| Acurite 592TXR/Tower | 433.92 | OOK | 56 bit (7B) | PWM 短220µs/长408µs | 8bit 加和 + 偶校验位 | 优（≤5kbps） | rtl_433 `acurite.c` 文件头 |
| Nexus TH | 433.92 | OOK | 36 bit | PPM 500µs 脉冲+1000/2000µs 间隔 | 无（固定 0xF nibble+重复 12 帧） | 优（~2kbps） | rtl_433 `nexus.c` 文件头 |
| Kerui/EV1527 | 433.92 | OOK | 24+1 bit | PWM 短304-560µs/长860-1016µs | 无（重复 25 帧） | 优 | rtl_433 `kerui.c` 文件头 |
| Fine Offset WH2 | 433.92 | OOK | 48 bit | PWM 500µs 固定脉宽 | CRC-8 (poly 0x31) | 优 | rtl_433 `fineoffset.c` 文件头 |
| LaCrosse TX141TH-Bv2 | 433.92 | OOK | 40 bit | PWM 固定 625µs 周期 | LFSR digest (0x31/0xf4 反射) | 优 | rtl_433 `lacrosse_tx141x.c` 文件头 |
| Oregon Scientific v1 | 433.92 | OOK | 32 bit | Manchester（标称 2930µs 位宽） | 和校验 | 差（位宽 2.9ms 太慢，同步序列异常） | rtl_433 `oregon_scientific_v1.c` 文件头 |
| WT450 | 433.92 | FM 编码 | 36 bit | 2ms 时钟、电平翻转=1 | 无 | 不适用（非 OOK） | rtl_433 `wt450.c` 文件头 |

> 来源说明：上表调制参数与字段布局均取自 rtl_433 各 `.c` 文件头协议注释（GPL-2.0，仅引用「协议格式」这一公开事实，未复制任何解码代码）。rtl_433 设备清单见 `include/rtl_433_devices.h`。

---

## 2. 选型协议帧格式

### 2.1 Acurite 592TXR / Tower（温湿度）

**调制与位编码（OOK-PWM）**：

| 参数 | 值 |
|------|-----|
| 短脉冲 | 220 µs 高 + 392 µs 低 |
| 长脉冲 | 408 µs 高 + 204 µs 低 |
| 同步脉冲 | 620 µs 高 + 596 µs 低 |
| 包间隔 | ~2192 µs（reset 取 4000 µs） |
| 位极性 | 解码前整体取反（rtl_433 对 bitbuffer 做 invert） |

**帧布局（56 bit = 7 字节，MSB 先，取反后）**：

```
Byte0      Byte1      Byte2      Byte3      Byte4      Byte5      Byte6
CCII IIII  IIII IIII  pB mmmmmm  pHHH HHHH  pTTT TTTT  pTTT TTTT  KKKK KKKK
└ channel ┘└─ 14bit ─┘ │ └type┘    └humidity┘ └─ temp 14bit(取低11) ┘ └校验和┘
                      └ battery: 1=OK 0=LOW
```

| 字段 | 位宽 | 位置 | 说明 |
|------|------|------|------|
| channel | 2 | bb[0] bit7:6 | 00=C, 10=B, 11=A（01 非法） |
| id | 14 | bb[0] bit5:0 + bb[1] | 传感器静态 ID |
| battery | 1 | bb[2] bit6 | 1=OK, 0=LOW |
| message_type | 6 | bb[2] bit5:0 | Tower 固定 0x04 |
| humidity | 7 | bb[3] bit6:0 | 相对湿度 %（1-99，>100 非法） |
| temperature | 11(14) | bb[4] bit6:0 + bb[5] bit6:0 | temp_raw = (bb[4]&0x7F)<<7 \| (bb[5]&0x7F)，temp_c = (temp_raw - 1000) * 0.1 |
| checksum | 8 | bb[6] | 前 6 字节加和 mod 256 |

**校验**：
1. 加和校验：`sum(bb[0..5]) & 0xFF == bb[6]`
2. 偶校验位：bb[2]~bb[5] 每个字节 bit7 为其低 7 位的偶校验（`parity = 0` 表示通过）

### 2.2 Nexus TH（温湿度，PPM 距离编码）

**调制与位编码（OOK-PPM）**：

| 参数 | 值 |
|------|-----|
| 脉冲 | ~500 µs 高 |
| bit 0 | 500 µs 高 + ~1000 µs 低 |
| bit 1 | 500 µs 高 + ~2000 µs 低 |
| 同步间隔 | ~4000 µs |
| 重复 | 每包 12 次 |

**帧布局（36 bit = 9 nibble，MSB 先）**：

```
[id0][id1][flags][temp0][temp1][temp2][const][humi0][humi1]
 B T C C
 4 4 4  4    4     4      4    4   4    4    4    4   ← nibble 位宽
```

| 字段 | 位宽 | 位置 | 说明 |
|------|------|------|------|
| id | 8 | nibble0-1 | 换电池时随机变化 |
| battery | 1 | flags bit3 | 1=OK, 0=LOW |
| test | 1 | flags bit2 | 0=正常 |
| channel | 2 | flags bit1:0 | 0=CH1, 1=CH2, 2=CH3 |
| temperature | 12 | nibble3-5 | 有符号 12bit 二进制补码 ×0.1（摄氏）：temp_c = signed12 * 0.1 |
| const | 4 | nibble6 | 固定 0xF |
| humidity | 8 | nibble7-8 | 相对湿度 % |

**校验**：无常规校验和；以「const nibble == 0xF」+「12 次重复帧一致」做完整性判据。

### 2.3 Kerui / EV1527（门磁·PIR 安防，x1527 型）

**调制与位编码（OOK-PWM，固定 24bit ID 型）**：

| 参数 | 值 |
|------|-----|
| 短脉冲 | 304-560 µs（新器件 340 µs） |
| 长脉冲 | 860-1016 µs |
| 同步 | 前置宽间隔同步位（作为第 25 个数据位忽略） |
| 重复 | 每包 25 帧 |

**帧布局（24 bit）**：

```
[ 20bit 地址 / ID ] [ 4bit 命令 ]
```

| 字段 | 位宽 | 位置 | 说明 |
|------|------|------|------|
| id | 20 | bit23..4 | EV1527 编码地址（每颗芯片固定） |
| cmd | 4 | bit3..0 | 命令码：开门/关门/报警/电池低等 |

**校验**：无校验；以「25 次重复帧一致 + 非全零」做判据。EV1527 是 1527/PT2262 家族通用遥控编码，可直接接「门磁 / PIR / 水浸 / 遥控器」。

---

## 3. SX1278 OOK 寄存器级配置建议

SX1278（Semtech SX1276/77/78 家族）FSK/OOK 模式寄存器（地址以 datasheet 为准，与 RadioLib 常量一致）：

| 寄存器 | 地址 | 建议值 | 说明 |
|--------|------|--------|------|
| RegOpMode | 0x01 | 0x00→LongRangeMode=0, ModulationType[6:5]=0b01 (OOK) | 进 FSK/OOK 非 LoRa 模式 |
| RegRxBw | 0x12 | Mant=0b10(20), Exp=0b100 → 25 kHz（Acurite/Kerui）；Exp=0b101 → 12.5 kHz（Nexus 慢速可换） | 带宽：RxBw = 32MHz/(Mant·2^(Exp+2)) kHz |
| RegLna | 0x0C | LnaBoost=0b11(150% 电流) + LnaGain=0b001(G1 最大增益) | 提高 OOK 灵敏度 |
| RegOokPeak | 0x14 | ThreshType[4:3]=0b00(fixed)，PeakStep=0b000 | 固定门限判 OOK 电平，避免峰值漂移 |
| RegOokFix | 0x15 | 0x06~0x0A（按 RSSI 底噪标定） | OOK 固定门限值 |
| RegRssiConfig | 0x0E | RssiSmoothing=0b000(2 样本，最快响应) | 脉冲边沿时延最小 |
| RegRssiThresh | 0x10 | 0x80（= -64 dBm 门限） | RssiThreshold = 值/2 dBm |
| RegRssiValue_FSK | 0x11 | 只读 | 实时 RSSI，脉冲包络采样 |

**关键结论**：
1. **OOK 可收**：SX1278 的 `ModulationType=OOK`（RegOpMode[6:5]=0b01）+ `RegOokPeak/RegOokFix` 固定门限，配合 RSSI 快速采样即可恢复脉冲包络，无需 SDR 的 IQ 采样——满足本阶段 433MHz OOK 传感器。
2. **灵敏度**：datasheet 典型 OOK 灵敏度约 **-111 dBm @ 1.2kbps**（LNA Boost + 窄带宽下可达 -117 dBm 量级），与工单给的 -112 dBm@1.2kbps 一致；配合 LnaBoost + RxBw 25kHz 可覆盖 Acurite/EV1527，Nexus 可再收窄到 12.5kHz 提灵敏度。
3. **AGC**：OOK 不用 LnaGain 自适应（FSK 用 AGC）；OOK 采用 **LnaBoost 常开 + 固定增益 G1**，由固定 OOK 门限判高低电平。RSSI 平滑设为 2 样本最小化边沿抖动。
4. **固件框架选型 = Arduino**：单核 tight-loop 轮询 RSSI 边沿（ESP32-S3 240MHz，SPI 8MHz 读一次寄存器 ~2-3µs，时间分辨率 ~10-20µs，足够分辨 200µs 以上脉冲）；不引 WiFi/蓝牙，纯 USB-CDC 串口上报。Arduino-esp32 core 比裸 ESP-IDF 更轻、构建链更简单，满足「不引入 RTOS 重型依赖」（不用 Zephyr/FreeRTOS+TCP 等中间件）。

---

## 4. 参考来源（真实）

1. rtl_433 设备清单：`https://github.com/merbanan/rtl_433/blob/master/include/rtl_433_devices.h`
2. rtl_433 `src/devices/acurite.c` 文件头协议注释（调制参数、字段布局、校验、偶校验）
3. rtl_433 `src/devices/nexus.c` 文件头（PPM 距离编码、36bit nibble 布局）
4. rtl_433 `src/devices/kerui.c` 文件头（x1527 24bit、脉冲时序、25 帧重复）
5. rtl_433 `src/devices/fineoffset.c` / `lacrosse_tx141x.c` / `oregon_scientific_v1.c` / `wt450.c` 文件头（候选协议）
6. Semtech SX1276/77/78 Datasheet（RegOpMode/RegRxBw/RegLna/RegOokPeak/RegOokFix/RegRssi* 寄存器语义、OOK 灵敏度）
7. RadioLib `src/modules/SX127x/SX127x.h`（寄存器地址与位域常量，与 datasheet 一致，公开 MIT 源）

> GPL 声明：本报告仅引用协议格式事实（不受版权保护），独立实现于 N-02/N-03，主仓不落任何 GPL 代码。
