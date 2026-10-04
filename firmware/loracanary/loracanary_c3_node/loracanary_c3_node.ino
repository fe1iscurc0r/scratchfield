/* LoRaCanary v1.5 · ESP32-C3 轻量节点固件（AB-02 采集上报 + AB-03 深度睡眠）。
 *
 * 合宙 ESP32-C3 插接模块 + NEO-6M + GY-BME280 + SX1278（Ra-02 类），接线见 node_config.h
 * 与 README「C3 接线图」。帧协议 = tools/lora_frame.py 的 C++ 镜像 loracanary_frame.*。
 *
 * 每周期（工单 AB-02 + AB-03）：
 *   定时器唤醒 → 外设上电（MOS，接口预留）→ GPS encode（≤2s 窗，热启动尽力）
 *   → BME280 采集 → 组装 GEO 帧(type=0x03) → LoRa 发送（433MHz SF7/BW125/CR4/5，
 *   13dBm≈20mW ≤100mW）→ 串口 JSON debug → 外设断电 → 深度睡眠(默认 60s)
 *
 * 深度睡眠（AB-03）：
 *   esp_sleep_enable_timer_wakeup(SLEEP_INTERVAL_S × 1e6) + esp_deep_sleep_start；
 *   RTC 保持 node_id/seq/epoch 跨唤醒不丢（rtc_state.*，掉电冷启动归零是预期）；
 *   SX1278 每次唤醒用 RST 软复位兜底（RadioLib begin 内部拉 RST）。
 *
 * 诚实降级（铁律）：
 *   - GPS 未定位（sat=0）→ GEO 帧 lat/lng/alt=0 照发，不造假坐标；
 *   - BME280 不在线 → MOCK 采样值 + JSON 带 "mock_bme":true 标注。
 *
 * GPS 热启动策略：外设每周期断电时 NEO-6M 无备份电 → 周期短会反复冷启动
 * （TTFF ~27s，必然先走 sat=0 降级几轮）；真机实测 TTFF/电流后可把
 * SLEEP_INTERVAL_S 调到 300（node_config.h），或给 GPS 供常电改用软件休眠。
 *
 * 参考 RadioLib 官方 SX1278 例程的 API 用法（GPL-3），本工程主代码独立实现；
 * MQTT/JSON 不上 LoRa 链路（二进制帧纪律），JSON 仅串口 debug。
 * 纯计算固件，无 LLM/网络调用。
 *
 * 构建：arduino-cli compile --fqbn esp32:esp32:esp32c3 firmware/loracanary/loracanary_c3_node
 */
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

#include <esp_sleep.h>

#include <Adafruit_BME280.h>
#include <RadioLib.h>
#include <TinyGPSPlus.h>

#include "node_config.h"
#include "loracanary_frame.h"
#include "rtc_state.h"

// ---- GPS（UART1，只收不发）----
static TinyGPSPlus s_gps;
static HardwareSerial s_gps_serial(1);

// ---- SX1278（RadioLib Module: CS, DIO0, RST, DIO1=NC）----
static SX1278 s_radio = new Module(PIN_LORA_CS, PIN_LORA_DIO0, PIN_LORA_RST,
                                   RADIOLIB_NC);

// ---- BME280 ----
static Adafruit_BME280 s_bme;      // I2C（0x76/0x77 探测）
static bool s_bme_ok = false;      // 真传感器在线
static bool s_bme_mock = false;    // MOCK 模式（诚实标注）

// ---- 状态 ----
static loracanary::NodeCounters s_cnt;  // RTC 保持计数（AB-03，rtc_load 推进）
static bool s_radio_ok = false;
static bool s_cold_boot = true;

// ---- 采样缓存 ----
static float  s_t = 0.0f, s_p = 0.0f;
static uint8_t s_h = 0;
static double s_lat = 0.0, s_lng = 0.0;
static int    s_alt = 0;
static uint8_t s_sat = 0;
static bool   s_fix = false;

// ---------------------------------------------------------------------------
// 初始化
// ---------------------------------------------------------------------------
// Adafruit_BME280::begin 包一层（地址自动探测轮询用）
static bool bmeBegin(uint8_t addr) {
  return s_bme.begin(addr);  // 默认 weather 监控模式（低过采样，够用）
}

static void bmeInit() {
  Wire.begin(PIN_BME_SDA, PIN_BME_SCL);
  // 地址自动探测（SPEC 假设表：0x76/0x77，SDO 引脚电平决定）
  const uint8_t addrs[2] = {0x76, 0x77};
  for (int i = 0; i < 2 && !s_bme_ok; i++) {
    s_bme_ok = bmeBegin(addrs[i]);
  }
  if (!s_bme_ok) {
    s_bme_mock = true;  // 无传感器 → MOCK（JSON 带 mock_bme:true，不静默造假）
    Serial.println("{\"src\":\"c3node\",\"event\":\"bme_mock\",\"note\":\"BME280 0x76/0x77 均不在线\"}");
  }
}

static void radioInit() {
  // ESP32-C3 默认 SPI 引脚不适用，显式重映射到 IO6..IO9
  SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_CS);
  if (!s_cold_boot) {
    // 深睡唤醒后 RST 软复位兜底（AB-03）：断电重启的模块可能处于未知态，
    // RadioLib SX127x::reset() 拉低 RST 引脚做硬复位，再进 begin
    s_radio.reset();
  }
  // 433MHz（业余 70cm / ISM 433.05-434.79MHz 内），SF7/BW125/CR4/5，功率 ≤100mW
  int16_t st = s_radio.begin(433.0, 125.0, 7, 5, RADIOLIB_SX127X_SYNC_WORD,
                             TX_POWER_DBM);
  s_radio_ok = (st == RADIOLIB_ERR_NONE);
  Serial.printf("{\"src\":\"c3node\",\"event\":\"radio_init\",\"state\":%d,\"ok\":%s}\n",
                st, s_radio_ok ? "true" : "false");
}

// ---------------------------------------------------------------------------
// 外设电源控制（MOS 管方案，代码留接口——AB-03 第 3 条）
// 宏未接线（-1）时跳过：裸模块靠自身静态电流，深睡电流以实测为准。
// 硬件注记：深睡时 GPIO 转高阻，MOS 栅极必须配偏置电阻把高阻态固定在
// 「断电」电平（高边 P-MOS：栅极上拉关断；低边 N-MOS：下拉关断），见 README。
// ---------------------------------------------------------------------------
static void periphGpio(int8_t pin, bool on) {
  if (pin < 0) {
    return;
  }
  pinMode(pin, OUTPUT);
  digitalWrite(pin, on ? PWR_ACTIVE_LEVEL : (PWR_ACTIVE_LEVEL ? 0 : 1));
}

static void periphPowerOn() {
  periphGpio(PWR_GPS_PIN, true);
  periphGpio(PWR_LORA_PIN, true);
  periphGpio(PWR_BME280_PIN, true);
  delay(50);  // 电源轨稳定 + NEO-6M 上电（真机按 MOS 选型可调）
}

static void periphPowerOff() {
  periphGpio(PWR_GPS_PIN, false);
  periphGpio(PWR_LORA_PIN, false);
  periphGpio(PWR_BME280_PIN, false);
}

void setup() {
  Serial.begin(115200);
  delay(200);  // CDC 枚举等待（合宙板 USB 串口）

  // AB-03：RTC 计数恢复 + 冷/热唤醒判定（打印进 boot JSON 供真机核对不丢计数）
  s_cold_boot = loracanary::rtc_load(&s_cnt);

  Serial.printf("{\"src\":\"c3node\",\"event\":\"boot\",\"fw\":\"v1.5-ab03\","
                "\"node_id\":%u,\"wake\":\"%s\",\"seq\":%lu,\"epoch\":%lu}\n",
                NODE_ID, s_cold_boot ? "cold" : "timer",
                (unsigned long)s_cnt.seq, (unsigned long)s_cnt.epoch);

  periphPowerOn();
  s_gps_serial.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
  bmeInit();
  radioInit();
}

// ---------------------------------------------------------------------------
// 采集
// ---------------------------------------------------------------------------
// GPS 采集：≤2s 窗口（热启动尽力）。拿到有效 fix 提前退出；
// 超时无 fix → sat=0 降级（lat/lng/alt 全 0）。真机实测 TTFF 后可调周期 300s：
// 冷启动（首次上电/long off）TTFF 典型 ~27s，必然走降级几轮后转热启动 ~1s。
static void gpsCollect() {
  s_fix = false;
  s_lat = 0.0;
  s_lng = 0.0;
  s_alt = 0;
  s_sat = 0;
  uint32_t t0 = millis();
  while (millis() - t0 < GPS_FIX_WINDOW_MS) {
    while (s_gps_serial.available() > 0) {
      s_gps.encode(s_gps_serial.read());
    }
    if (s_gps.location.isValid()) {
      s_lat = s_gps.location.lat();
      s_lng = s_gps.location.lng();
      if (s_gps.altitude.isValid()) {
        s_alt = (int)lround(s_gps.altitude.meters());
      }
      s_sat = s_gps.satellites.isValid() ? (uint8_t)s_gps.satellites.value() : 0;
      s_fix = (s_sat > 0);  // 有坐标且见星才算真 fix
      break;
    }
    delay(2);  // 让 IDLE 轮询喂狗
  }
}

// BME280 采集；MOCK 模式填采样占位值并标注（不读总线）
static void bmeCollect() {
  if (s_bme_ok) {
    s_t = s_bme.readTemperature();                      // ℃
    s_h = (uint8_t)lroundf(s_bme.readHumidity());       // %（1% 分辨率，帧协议勘误）
    s_p = s_bme.readPressure() / 100.0f;                // Pa → hPa
    return;
  }
  s_bme_mock = true;
  s_t = 25.0f;
  s_h = 55;
  s_p = 1013.2f;  // MOCK 采样占位值——真传感器接入后自动消失
}

// ---------------------------------------------------------------------------
// 上报：组装 GEO 帧 → LoRa TX → 串口 JSON debug
// ---------------------------------------------------------------------------
static void reportOnce() {
  gpsCollect();
  bmeCollect();

  // GEO payload 定长 18B（lat/lng/alt int32/int16 定点，sat=0 时镜像内部强制清零）
  uint8_t payload[LC_GEO_PAYLOAD_LEN];
  size_t pn = lc_build_geo_payload(s_t, s_h, s_p, s_lat, s_lng, (int16_t)s_alt,
                                   s_sat, payload);
  uint8_t frame[LC_GEO_FRAME_LEN];
  size_t fn = (pn == LC_GEO_PAYLOAD_LEN)
                  ? lc_build_frame(LC_TYPE_GEO, (uint8_t)(s_cnt.seq & 0xFF),
                                   NODE_ID, payload, pn, frame, sizeof(frame))
                  : 0;

  int16_t tx_state = RADIOLIB_ERR_NONE;
  if (s_radio_ok && fn == LC_GEO_FRAME_LEN) {
    tx_state = s_radio.transmit(frame, fn);  // 阻塞发送，含重试由上层心跳计数兜底
  } else {
    tx_state = RADIOLIB_ERR_CHIP_NOT_FOUND;  // 诚实标注初始化失败/帧构造失败
  }

  // 串口 JSON debug（python json.loads 可解析；上行 JSON 由网关负责，这里带采集元数据）
  char line[256];
  snprintf(line, sizeof(line),
           "{\"src\":\"c3node\",\"node_id\":%u,\"seq\":%lu,"
           "\"t\":%.2f,\"h\":%.1f,\"p\":%.2f,"
           "\"lat\":%.7f,\"lng\":%.7f,\"alt\":%d,\"sat\":%u,\"gps_fix\":%s,"
           "\"mock_bme\":%s,\"tx_ok\":%s,\"tx_state\":%d}",
           NODE_ID, (unsigned long)s_cnt.seq,
           (double)s_t, (double)s_h, (double)s_p,
           s_lat, s_lng, s_alt, s_sat, s_fix ? "true" : "false",
           s_bme_mock ? "true" : "false",
           tx_state == RADIOLIB_ERR_NONE ? "true" : "false", tx_state);
  Serial.println(line);

  s_cnt.seq++;  // 发送与否都推进计数（心跳语义，v1 兼容）
}

void loop() {
  reportOnce();

  // ---- AB-03：深度睡眠（本函数不再返回）----
  // 外设断电 → 计数写 RTC → 定时器唤醒 → esp_deep_sleep_start。
  // 周期 SLEEP_INTERVAL_S（默认 60s）在 node_config.h；真机实测 GPS TTFF/
  // 深睡电流后可调 300s（注释即契约，改动同步 SPEC v1.5 第三节）。
  periphPowerOff();
  loracanary::rtc_commit(&s_cnt);
  Serial.flush();  // 冲完 debug 行再睡（CDC 断开也不丢本条）
  esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_INTERVAL_S * 1000000ULL);
  esp_deep_sleep_start();  // 不返回；唤醒后从 setup() 重新开始
}
