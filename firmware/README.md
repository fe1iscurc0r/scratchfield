# 哨兵网格 N-03 · ESP32-S3 边缘频谱哨兵固件

把 ESP32-S3 + SX1278 变成"会解码 433MHz 传感器的频谱哨兵"：
SX1278 OOK 收包 → 脉冲宽度测量 → PWM 分类（500/1000us）→ Acurite 解码 → 串口 NDJSON。

## 接线图（SX1278 ↔ ESP32-S3 SuperMini）

| SX1278 引脚 | ESP32-S3 SuperMini | 说明 |
|-------------|-------------------|------|
| VCC | 3V3 | 供电（SX1278 3.3V，勿接 5V） |
| GND | GND | 共地 |
| SCK | GPIO 12 | SPI 时钟 |
| MISO | GPIO 13 | SPI 主入从出 |
| MOSI | GPIO 11 | SPI 主出从入 |
| NSS (CS) | GPIO 10 | SPI 片选 |
| RST | GPIO 9 | 复位 |
| DIO0 | GPIO 5 | RadioLib 默认 |
| DIO1 | GPIO 6 | OOK 载波边沿中断（脉冲测量） |
| ANT | 433MHz 天线 | 中心频 433.92MHz |

> 引脚可改，改完同步 `src/main.cpp` 顶部 `PIN_*` 宏。

## 烧录

```bash
# 天选7 Windows 侧（PowerShell），或云服装了 PlatformIO 后同命令
cd firmware
pio run -t upload          # 编译 + 烧录
pio device monitor         # 打开串口监视器（115200）
```

云服无 ESP32 工具链，`pio run` 首次会拉 platform-espressif32 + RadioLib 依赖。

## 串口协议（USB-CDC，115200）

固件启动自报 + 收到传感器包后，每行一条 NDJSON：

```json
{"src":"sentinel","ready":true}
{"src":"sentinel","protocol":"acurite-tower","id":4660,"channel":"C","temperature_c":25.0,"humidity_pct":50,"battery":"OK","crc_ok":true}
{"src":"sentinel","protocol":"acurite-515","kind":"fridge","id":2748,"temperature_f":32.0,"crc_ok":true}
```

串口命令（发一行 + 回车）：

| 命令 | 返回 |
|------|------|
| `STATUS` | 固件频率/带宽/比特率配置 |
| `RESET` | 清空脉冲缓冲 |

## 真机验证点（用户按序实测）

1. **上电自检**：串口出 `{"ready":true}`，无 `error` 字段。
2. **寄存器确认**：发 `STATUS`，返回 freq 433.92 / bw 250 / bitrate 1.2。
3. **收真实信号**：淘宝/闲鱼一块 Acurite 592TXR 温湿度传感器（约 20-40 元），
   放在天线旁 1-3 米，串口应出 `acurite-tower` 行，温度湿度与实物对比
   （误差 ±1°C / ±5%RH 内）。
4. **校验生效**：`crc_ok` 应恒为 `true`；故意远离/遮挡看是否丢帧或 `false`。

## 已知限制（诚实标注）

- **未编译验证**：云服无 ESP32 工具链，本工程未经 `pio run` 编译。
  首次真机编译若报 RadioLib API 差异（6.x vs 7.x 的 `setOOK`/`receiveDirect`
  签名），按编译错误微调即可。
- **脉冲精度**：当前用 `micros()` 粗测脉冲宽度（±4us 抖动），500/1000us
  分类有余量。若真机误码率高，换 ESP32 RMT 外设做硬件级脉冲捕获。
- **温度公式待校准**：`(raw-1000)/10` 基于公开文档自洽解读，真机样本
  到位后若偏差，只改 `decode_and_report` 里温度换算一行。

## 文件结构

```
firmware/
├── platformio.ini     # PlatformIO 工程（Arduino 框架 + RadioLib）
├── src/main.cpp       # OOK 接收 + 脉冲分类 + Acurite 解码 + NDJSON 输出
└── README.md          # 本文件
```
