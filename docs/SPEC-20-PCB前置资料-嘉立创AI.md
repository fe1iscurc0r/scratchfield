# SPEC-20 · PCB 前置资料包 · 给嘉立创 AI（LoRaCanary 底板 v0.6 直焊版）

> 用途：喂给立创 EDA 专业版 AI 助手的完整上下文 + 接线事实。AI 布局前先读这份，减少翻车。
> 器件策略（用户拍板）：**能直焊芯片的直焊，射频和主控保留模块化**。

---

## 一、器件策略总表

| 器件 | 方案 | 理由 | 来源 |
|---|---|---|---|
| ESP32-S3 SuperMini 核心板 | 排母插接（2×17pin 2.54mm） | 自带 USB/晶振/Flash/启动电路，直焊 S3 芯片复杂度爆炸 | 已有 ×2 |
| SX1278 LoRa 模块（Ra-01 风格 8pin） | 排母插接（2×4pin） | 射频匹配/天线由模块承担，直焊芯片要 50Ω 阻抗+天线网络，AI 必翻车 | 已有 ×2 |
| BME280 温湿压芯片 | **直焊**（LGA8 2.5×2.5mm） | GY 模块 ¥18 又大，芯片 ¥3-5；I2C 外围极简（2 上拉+1 去耦） | 补购 ~2 片 |
| AMS1117-3.3 LDO | **直焊**（SOT-223） | 已是裸芯片，10 片储备直接用 | 已有 ×10 |
| TP4056 锂电充电 | **直焊**（ESOP-8） | 模块版占高，芯片+4 电阻+2 LED 即可 | 已有模块×5，补芯片或拆 |
| SSD1306 OLED 0.96" | 排母插接（4pin I2C） | 玻璃屏没法直焊，买带排针的屏模块 | 已有 ×3 |
| USB Type-C 母座（16pin 带 CC 电阻） | 直焊 | 供电+调试串口 | 补购 |
| 18650 电池座（单节带线 or 焊片） | 直焊 | 已有电池盒×4 可用（v0.5 可先不做电池） | 已有 |
| 轻触按钮×2 / LED×2 / 330Ω / 100nF×6 / 10uF / 4.7k×2 / 1k×2 | 直焊 | 标准件 | 电容已有 0805 |

## 二、关键 IC 事实（AI 画原理图用）

### BME280（LGA8 2.5×2.5mm，I2C）
- 引脚：VDD / GND / SDA / SCL / CSB(接 VDD 选 I2C) / SDO(地址选择) / 空脚×2
- I2C 地址：SDO 接地 → 0x76；SDO 接 VDD → 0x77（推荐 0x76：SDO 接地）
- 外围：VDD 一颗 100nF；SDA/SCL 各一颗 4.7k 上拉到 3.3V
- 立创搜索：`BME280 LGA8 2.5x2.5`（优先选博世/BST 原厂或兼容）

### AMS1117-3.3（SOT-223）
- 引脚（正面丝印朝自己，左→右）：GND / VOUT / VIN；背面大焊盘 = VOUT
- 输入 ≤12V，输出 3.3V，最大 1A；输入输出各一颗 10uF/100nF
- 立创搜索：`AMS1117-3.3 SOT-223`（注意选 3.3V 固定输出版）

### TP4056（ESOP-8）
- 引脚：1=TEMP 2=PROG 3=GND 4=VCC(5V) 5= BAT 6=STDBY(LED) 7=CHRG(LED) 8=CE
- 外围：PROG 接 Rprog（1.2k→1A 充电）；BAT/GND 各接 18650 电池±；VCC 接 5V
- 立创搜索：`TP4056 ESOP-8`

### SX1278 Ra-01 模块（2×4 排针，8pin）
| 引脚 | 功能 | 接 ESP32-S3（SuperMini）GPIO |
|---|---|---|
| VCC | 3.3V（**只吃 3.3V，接 5V 烧**） | 3V3 |
| GND | 地 | GND |
| NSS | SPI 片选 | GPIO10 |
| SCK | SPI 时钟 | GPIO12 |
| MOSI | SPI 主出从入 | GPIO11 |
| MISO | SPI 主入从出 | GPIO13 |
| RST | 复位 | GPIO4 |
| DIO0 | 中断（RX/TX 完成） | GPIO2 |
- 天线：模块自带 IPEX 座或弹簧焊盘；补购 433MHz 弹簧天线或 IPEX 天线

### ESP32-S3 SuperMini（2×17pin 排母插接）
- 板上丝印面：两侧各 17pin，含 3V3 / GND / 5V / 32 个 GPIO
- 关键引脚（本项目用）：
  - 供电输入：5V（USB 进来时此脚为 5V；外部 3.3V 可接 3V3 脚）——**底板只给 3V3 和 GND 就够**（SuperMini 板载 LDO 会从 USB 5V 稳压）
  - 实际上：**v0.6 底板方案 = USB-C 5V → 直接进 SuperMini 的 5V 脚**，SuperMini 板载 LDO 出 3.3V 给底板 3.3V 轨 → BME280/SX1278/OLED。这样 AMS1117 都可以省（用户拍板直焊 AMS1117 当备份方案，两路都画：USB 5V 经 AMS1117 → 3.3V 轨 + SuperMini 5V 直通，二极管防倒灌）
  - I2C：SDA=GPIO8，SCL=GPIO9（接 BME280 + OLED 共用总线）
  - SPI（SX1278）：NSS=10 SCK=12 MOSI=11 MISO=13（软件可配，见上表）
  - 板载 RGB LED：GPIO48（可作状态灯，不用接外部 LED）

## 三、完整网络清单（Netlist，AI 直接照画）

```
电源：
  USB-C VBUS ──┬─→ TP4056 VCC (5V 充电路径)
               └─→ D1(SS34 肖特基) ──→ SuperMini 5V 脚
  TP4056 BAT ──→ 18650 电池正（+）
  TP4056 BAT ──→ AMS1117 VIN（可选，电池 3.7-4.2V 降压 3.3）
  USB-C VBUS ──→ AMS1117 VIN（双供电，肖特基隔离）
  AMS1117 VOUT → 3.3V 轨（BME280/SX1278/OLED 上拉）
  GND 全连接：USB-C GND / TP4056 GND / AMS1117 GND / SX1278 GND / OLED GND / SuperMini GND

I2C 总线（GPIO8/GPIO9）：
  SDA: SuperMini GPIO8 ──→ BME280 SDA ──→ OLED SDA ──→ 4.7k→3.3V
  SCL: SuperMini GPIO9 ──→ BME280 SCL ──→ OLED SCL ──→ 4.7k→3.3V

SPI（GPIO10/11/12/13 + RST4 + DIO0_2）：
  SuperMini GPIO10 → SX1278 NSS
  SuperMini GPIO11 → SX1278 MOSI
  SuperMini GPIO12 → SX1278 SCK
  SuperMini GPIO13 → SX1278 MISO
  SuperMini GPIO4  → SX1278 RST
  SuperMini GPIO2  → SX1278 DIO0

控制/指示：
  BOOT 按钮：一端接 SuperMini GPIO0，一端 GND（板载上拉）
  RST 按钮：一端接 SuperMini EN，一端 GND
  LED(电源)：0603/0805 LED + 330Ω → 3.3V（可选）
  板载 RGB GPIO48 免外部 LED
```

## 四、给嘉立创 AI 的完整提示词（复制用）

```
【项目】LoRa 环境感知节点底板（LoRaCanary v0.6）。2 层板、60×50mm、成本敏感。
【设计原则】模块化插接（主控/LoRa/屏）+ 直焊芯片（传感器/LDO/充电）。所有网络名按规范命名（3V3/GND/SDA/SCL/LORA_NSS 等）。

【板上器件】
1. ESP32-S3 SuperMini 核心板排母：2×17pin 2.54mm，居中偏上。供电脚接 3V3/5V/GND。
2. SX1278 Ra-01 模块排母：2×4pin，右上角，天线朝板边，天线投影区净空≥5mm 底部禁铜。SPI 接 LORA_NSS=GPIO10/SCK=GPIO12/MOSI=GPIO11/MISO=GPIO13/RST=GPIO4/DIO0=GPIO2。
3. BME280 芯片（LGA8）直焊：放右侧中部，接 I2C：SDA=GPIO8/SCL=GPIO9，SDO 接地（地址 0x76），VDD 旁 100nF，SDA/SCL 各 4.7k 上拉 3.3V。
4. SSD1306 OLED 0.96" 4pin 排母：右侧，接同一 I2C 总线。
5. AMS1117-3.3（SOT-223）直焊：左下角，VIN 接 USB 5V（肖特基隔离），VOUT→3V3 轨，输入输出各 10uF+100nF。
6. TP4056（ESOP-8）直焊：左下，VCC 接 5V，PROG 1.2k，BAT 接 18650 电池座+，CHRG/STDBY 各接 LED+330Ω。
7. USB Type-C 母座：左边缘，VBUS→TP4056 VCC+肖特基→SuperMini 5V/GND。
8. BOOT 按钮(GPIO0→GND)、RST 按钮(EN→GND)，放 SuperMini 排母旁。
9. 电容：每个 IC 电源脚旁 100nF；电源输入 10uF。

【布局规则】电源区左下；SX1278 右上角天线净空；3V3 走线≥0.5mm；底层铺地、天线投影区禁铜；四角 M3 螺丝孔 3.2mm；排母统一朝上方便插模块。
【布线】信号线 0.3mm；I2C 总线靠近；SX1278 下方短走线。
【输出】DRC 0 错误 0 警告；注释中文；给出 BOM 表。
```

## 五、补购清单（可选，凑立创包邮门槛用）

- BME280 芯片 LGA8 ×2（~¥3/片）
- Type-C 16pin 母座 ×2
- SS34 肖特基 ×4（电源隔离）
- 433MHz 弹簧天线 / IPEX 座 ×2（SX1278 用）
- 排母 2×17 / 2×4 / 1×4 若干、排针若干
- 电阻电容套件：4.7k×20、1k×20、330Ω×10、10uF×10（都在立创 0805 基础库）
- TP4056 芯片 ESOP-8 ×2（或直接拆手上 TP4056 模块的芯片，麻烦就补购）

## 六、提醒（AI 容易踩的坑）

1. **SX1278 只吃 3.3V**——网络里绝不能把 5V 接进 SX1278
2. BME280 地址 0x76（SDO 接地），忘了接 SDO 会导致地址飘到 0x77 或悬空
3. SuperMini 排母的 3V3/GND/5V 位置以**实物丝印为准**（不同批次有差异），AI 画完人核对排母 1 脚方向
4. TP4056 的 BAT 脚严禁反接 18650（防反接在电池座加二极管或机械防呆）
5. I2C 上拉电阻放 BME280 附近，别隔着板子拉线