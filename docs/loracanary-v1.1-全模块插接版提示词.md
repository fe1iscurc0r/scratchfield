# LoRaCanary v1.1 插接版（全模块化）· 嘉立创 AI 绘图提示词 · 2026-10-01 修订

> 背景：v1.0 板两个设计缺陷（U1 用了 BTB 座无配套公座、U2 按 SX1278 裸芯片画）。
> 本版原则：**所有器件焊盘必须匹配手头实物（全是成品模块），禁止 AI 自行替换封装**。

---

## 复制给嘉立创 AI 的提示词

```
【项目】LoRa 环境感知节点底板 LoRaCanary v1.1-全模块插接版。2 层板 70×60mm。
【硬性约束】所有插座用 2.54mm 间距排母/排针，禁止使用板对板(BTB)连接器、禁止任何芯片直焊焊盘（QFN/LGA/ESOP 全部不要），所有器件位都是插座或直插焊盘。

【器件——每个焊盘按描述的实物形态画】
1. U1 主控座：2.54mm 双排排母 2×17P，围出约 22.5×18mm 矩形区域（ESP32-S3 SuperMini 开发板邮票孔直插）。引脚定义按 ESP32-S3 SuperMini 标准引脚排列：3V3/GND/5V + GPIO0-GPIO21 常规布局。
2. U2 LoRa 座：2.54mm 双排排母 2×8P，间距 17mm×22.5mm 区域（Ra-01 模块 29×17mm 直插；Ra-01 为 16pin 半孔模块，两排 8 脚，脚距 2.54mm）。
3. U3 BME280 座：2.54mm 单排排母 1×4P（VCC/GND/SCL/SDA，BME280 模块直插）。
4. U4 AMS1117 模块座：2.54mm 单排排母 1×3P（VIN/GND/VOUT，AMS1117 小模块直插）。
5. U5 TP4056 模块座：2.54mm 单排排母 1×6P（TP4056 充电模块带 OUT+/OUT-/IN+/IN- 直插）。
6. U6 OLED 座：2.54mm 单排排母 1×4P（GND/VCC/SCL/SDA，0.96寸 SSD1306 直插）。
7. J1 USB-C 16P 沉板母座（仅供电 5V，CC 脚各接 5.1kΩ 下拉）。
8. SW1/SW2 轻触开关 6×6×5 贴片（BOOT/RST）。
9. LED1-3 0805 + 330Ω/470Ω 限流电阻。
10. R1/R2 4.7kΩ 0805（I2C 上拉）、R7/R8 5.1kΩ 0805（CC）、R3 1.2kΩ 0805（备用）。
11. C1-C5 100nF/10uF 0805（各插座供电退耦）。
12. SS34 SMA（5V 隔离）、SMAJ5.0A TVS、自恢复保险丝 1206 33V/0.5A。
13. B1 电池座：18650 弹片座或 KF332-2P 端子。
14. ANT 天线座：SMA 母座直插（给 Ra-01 天线引出，Ra-01 板载 ANT 焊盘飞线到 SMA 中心脚，丝印标注飞线）。

【连接】
- 电源：USB-C 5V → 保险丝 → SS34 → AMS1117 模块 VIN；AMS1117 VOUT → 3V3 轨（给 SuperMini/BME280/OLED/Ra-01）。TP4056 模块 IN 接 USB-C 5V，OUT+ 接 SS34 前、OUT- 接地，18650 接 TP4056 BAT。若 TP4056 模块自带 USB 口则 J1 仅给 TP4056 模块供电（丝印二选一跳线焊盘）。
- I2C：GPIO8=SDA、GPIO9=SCL（SuperMini 引脚位标注），4.7k 上拉到 3V3，接 BME280 座 + OLED 座并联。
- SPI：GPIO10=NSS、GPIO12=SCK、GPIO11=MOSI、GPIO13=MISO、GPIO4=RST、GPIO2=DIO0，接到 Ra-01 座对应脚（NSS→NSS、SCK→SCK、MOSI→MOSI、MISO→MISO、RST→RST、DIO0→DIO0）。
- Ra-01 座 3.3V 脚接 3V3 轨，GND 脚接主地。

【布局】电源区左下（USB-C/保险丝/TP4056 座/18650）；SuperMini 座居中；Ra-01 座右上、天线朝板边、板边净空 ≥8mm 底部禁铜；I2C 座右侧一字排开；3V3 主走线 ≥0.5mm；底层整铺地；四角 M3 安装孔；所有插座丝印标注用途与引脚名。

【输出】DRC 0 错误；BOM 全部为插座/直插件/0805/SMA，无 QFN/LGA/BTB；中文注释。
```

---

## 下单核对清单（AI 出图后人工检查 4 点）

1. U1 位是不是 2×17P 大间距（2.54mm）排母焊盘、围出的矩形 ≥22×18mm —— 拿 SuperMini 实物比划
2. U2 位是不是 2×8P 排母、区域约 29×17mm —— 拿 Ra-01 实物比划
3. 全板搜一遍**没有任何细密小焊盘**（0.5/0.8mm 间距的都没有）
4. BOM 里没有 BTB/QFN/LGA 字样

任何一条不过 → 重新生成，不要下单。
