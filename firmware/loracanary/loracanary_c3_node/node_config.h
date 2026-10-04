/* LoRaCanary C3 节点 · 引脚/参数配置（合宙 ESP32-C3 插接模块，Arduino-ESP32）。
 *
 * 引脚照 SPEC-20 v1.5 第三节 + 工单 AB-02（合宙 C3 引脚表）：
 *   BME280  I2C: SDA=IO4  SCL=IO5（地址自动探测 0x76/0x77）
 *   SX1278  SPI: MOSI=IO6 MISO=IO7 SCK=IO8 CS=IO9 DIO0=IO10 RST=IO11
 *   NEO-6M  UART1: RX=IO3（接 GPS TX，9600 8N1）；TX=IO2 可不接（只收不发）
 *
 * 注意（诚实标注，README 同步）：
 *   - IO8/IO9 是 ESP32-C3 strapping 脚（SCK/CS 外设复用）：SCK 空闲电平、CS 上拉
 *     可能影响上电模式，若上电异常按 README「烧录步骤」断开 SPI 再上电排查。
 *   - SX1278 CS(IO9) 建议板加 10kΩ 上拉（低电平才选通，悬空误选通会烧发射电流）。
 *   - 外设电源控制脚为 MOS 管方案预留接口：未接线时置 -1，代码自动跳过（裸模块
 *     自身静态电流兜底）；真机接 MOS 后改宏即可断电深睡。
 */
#pragma once

// ---- node_id / 周期 ----
#define NODE_ID             1      // 节点号（uint8，1..32 v1 星型上限）
#define SLEEP_INTERVAL_S    60     // 上报周期（秒）；真机实测 GPS TTFF/电流后可调 300
#define GPS_FIX_WINDOW_MS   2000   // GPS 定位等待窗 ≤2s（工单 AB-02）
#define TX_POWER_DBM        13     // 433MHz 发射功率 13dBm≈20mW ≤100mW（铁律不超配）

// ---- BME280 I2C ----
#define PIN_BME_SDA         4
#define PIN_BME_SCL         5

// ---- SX1278 SPI ----
#define PIN_LORA_MOSI       6
#define PIN_LORA_MISO       7
#define PIN_LORA_SCK        8
#define PIN_LORA_CS         9
#define PIN_LORA_DIO0       10
#define PIN_LORA_RST        11

// ---- NEO-6M GPS（UART1） ----
#define PIN_GPS_RX          3      // C3 侧 RX ← NEO-6M TX
#define PIN_GPS_TX          2      // C3 侧 TX → NEO-6M RX（可不接，仅占位）
#define GPS_BAUD            9600

// ---- 外设电源控制（MOS 管方案，代码留接口；-1 = 未接，跳过） ----
#define PWR_GPS_PIN         1      // MOS 栅极：高=供电（P-MOS 低边开关反相时改极性宏）
#define PWR_LORA_PIN        (-1)   // SX1278/BME280 共 3.3V 轨时接同一个 MOS
#define PWR_BME280_PIN      (-1)
#define PWR_ACTIVE_LEVEL    1      // MOS 导通电平（高电平供电）；低边 P-MOS 电路改 0
