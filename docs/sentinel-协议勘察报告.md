# 哨兵网格 · 433MHz 传感器协议勘察报告（N-01）

> 源：SPEC-12 第七批 N-01。目的：确定 2~3 个 SX1278 OOK 可收、帧格式公开、解码逻辑可独立实现的 433MHz 传感器协议。
> 许可纪律：本报告只记录「协议格式事实」（调制方式/帧长/编码/校验/时序），这些是公开事实不受版权保护。rtl_433（GPL-2.0）仅作协议文档来源，解码逻辑后续独立实现，不复制其 C 代码。
> 结论先行：选型 **Acurite Tower (592TXR/06002) + Acurite 515 冰箱传感器 + LaCrosse TX141TH-Bv2** 三个，前两个同族共享帧头，一次实现覆盖两个。

---

## 一、候选协议对照表（5 个候选）

| 协议 | 频率 | 调制/编码 | 帧长 | 校验 | 公开文档 | SX1278 OOK 可收？ | 结论 |
|------|------|-----------|------|------|----------|-------------------|------|
| Acurite Tower 592TXR/06002（温湿度） | 433.92MHz | OOK PWM | 7 字节 56bit | 8bit 校验和 + 逐字节奇偶 | gist 完整 bit 布局 | ✅ 短脉冲 500us/长脉冲 1000us | ✅ 首选 |
| Acurite 515（冰箱/冷冻） | 433.92MHz | OOK PWM | 6 字节 48bit | 8bit 校验和 + 奇偶 | 同上 gist | ✅ 同族 | ✅ 次选（帧最短，最易验证） |
| LaCrosse TX141TH-Bv2（温湿度） | 433.92MHz | OOK PWM | 41bit | 8bit 校验 | rtl_433 源码 + Arduino 论坛 | ✅ s=256/l=500/r=1888us | ✅ 候选（变体多，帧格式略乱） |
| Acurite 6045m（闪电检测） | 433.92MHz | OOK PWM | 9 字节 72bit | 校验和+奇偶 | gist | ✅ 同族 | ⚠️ 备选（帧长，验证需真闪电） |
| OSv1/门磁类（Interlogix 等） | 433.92MHz | OOK PWM | 25bit | 无/简单 | 分散 | ✅ 500/1000us | ⚠️ 备选（协议多厂分叉，先不做） |

**选型逻辑**：Acurite Tower + 515 同族（共享 CCII/ID/Battery/Type 帧头 + 校验和 + 奇偶双重校验），帧格式文档完整到 bit 级，PWM 时序 500/1000us 在 SX1278 OOK 带宽内。LaCrosse 作为独立第二厂商补充（不同校验算法，验证解码器通用性）。

---

## 二、Acurite 帧格式（Tower 592TXR，msg type 0x04，7 字节）

```
Byte 0    Byte 1    Byte 2    Byte 3    Byte 4    Byte 5    Byte 6
CCII IIII | IIII IIII | pB00 0100 | pHHH HHHH | p??T TTTT | pTTT TTTT | KKKK KKKK
```

- **C**: Channel（2bit）—— 00:C, 10:B, 11:A（01 非法）
- **I**: Device ID（14bit，工厂固定）
- **B**: Battery（1bit）—— 1=OK, 0=low
- **M**: Message type（6bit）—— 0x04=Tower 温湿度
- **T**: 温度 Celsius（14bit 可用，实际 11bit 够 -40~70°C），编码 = (Celsius + 1000) × 10
- **H**: 相对湿度 %（7bit）
- **K**: 校验和（8bit）= 前 6 字节求和取低 8 位
- **p**: 每字节奇偶校验位（字节 2 起每字节一个，校验该字节其余 7bit，偶校验）

**关键：T 是 14bit 跨字节**——Byte3 低 7bit（?TT TTTT）+ Byte4 的 p??T TTTT（4bit T）+ Byte5 的 pTTT TTTT（7bit T）= 需要跨 3 字节拼接。这是解码器的核心难点，实现时注意 bit 拼接顺序。

### Acurite 515 帧格式（msg type 0x08/0x09，6 字节）

```
Byte 0    Byte 1    Byte 2    Byte 3    Byte 4    Byte 5
CCII IIII | IIII IIII | pBMM MMMM | bTTT TTTT | bTTT TTTT | KKKK KKKK
```

- C: Channel（2bit），I: Device ID（14bit，易失，断电重置）
- M: 0x08=冰箱, 0x09=冷冻
- T: 温度 Fahrenheit（14bit），编码 = (F + 1480) × 10
- K: 校验和（8bit），b: 每字节奇偶

---

## 三、LaCrosse TX141TH-Bv2 帧格式（41bit）

- **OOK PWM 参数**（rtl_433 实测）：s=256us（短脉冲）, l=500us（长脉冲）, r=1888us（符号周期）
- 帧长 41bit（Bv3 变体 33bit，注意区分）
- 编码：PWM（窄脉冲=0，宽脉冲=1）
- 校验：8bit CRC（多项式与 Acurite 不同，独立实现时单独核对）
- 变体坑：TX141-Bv2 / Bv3 / TX141W 帧长和字段位有差异，Bv3 是 33bit。**N-02 只实现 Bv2（41bit），Bv3 标注待补**。

---

## 四、SX1278 OOK 模式配置建议（寄存器级）

目标：433.92MHz 收 PWM 500/1000us（Acurite）+ 256/500us（LaCrosse）。

| 参数 | 建议值 | 寄存器/说明 |
|------|--------|-------------|
| 中心频率 | 433.92MHz | RegFrf（Frf = f_osc / 32768 × 0.92MHz 换算） |
| 调制模式 | OOK | RegOpMode[6:5] = 01（OOK） |
| 数据率 | ~1.2kbps（Acurite）/ ~2.6kbps（LaCrosse） | RegBitrate，最低 0.6kbps 起；500us 脉冲 ≈ 2kbps 边沿，设 1.2kbps 兼容 |
| 接收带宽 | 250kHz | RegRxBw；PWM 边沿需要带宽，250k 够 500us 脉冲 |
| AGC | 开启 | RegOokPeak / AgcAutoOn；OOK 模式 RSSI 阈值需 AGC 稳定 |
| OOK 峰值检测 | 开启，阈值 ~6dB | RegOokPeak；OOK 无载波时噪声，靠峰值阈值判 0/1 |
| 灵敏度 | 约 -112dBm @1.2kbps | 数据手册典型值，实际受 AGC/带宽影响 |

**关键坑**：SX1278 OOK 模式不是"收到包给你 bit"——它输出的是**比特流 + RSSI**，PWM 脉冲的宽窄要自己在固件里按定时器测量。所以固件接收循环是：OOK 解调 → 测量脉冲高/低持续时间 → 500us/1000us 分类 → 重组成 bit。这是 N-03 的核心逻辑，N-02 的 pulse_demod 就是这个分类逻辑的 Python 版。

---

## 五、选型最终结论

| 优先级 | 协议 | 帧长 | 校验 | 落地价值 |
|--------|------|------|------|----------|
| P0 | Acurite Tower 592TXR | 56bit | 校验和+奇偶 | 最常见的 433MHz 温湿度传感器，真机易买易验证 |
| P0 | Acurite 515 | 48bit | 校验和+奇偶 | 同族，共享帧头，一次实现覆盖两个 |
| P1 | LaCrosse TX141TH-Bv2 | 41bit | CRC | 独立第二厂商，验证解码器通用性 |

**N-02 实现顺序**：先 Acurite 族（pulse_demod PWM 分类 + Tower/515 两个解码器），LaCrosse 放最后（CRC 算法单独核对）。

**真机验证点（给用户）**：
1. 淘宝/闲鱼一块 Acurite 592TXR 温湿度传感器（约 20-40 元）或 433MHz 门磁
2. SX1278 OOK 收包 → 串口 `STATUS` 返回 RSSI/寄存器 → 确认中心频 433.92MHz 已锁
3. 收到真实传感器包 → 串口 NDJSON 出 `temperature/humidity` 与实物对比（误差 ±1°C/±5%RH 内）

*—— 沈遥 · 协议不是密码，是公开的方言。SX1278 会听，就看会不会分类 🐾*
