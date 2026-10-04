/* LoRaCanary v1.5 · S3 网关固件（AB-04：GEO 帧解析 + 串口/WiFi MQTT 双上行）。
 *
 * ESP32-S3 SuperMini + SX1278（Ra-02 类），接线照 v1 firmware/README 引脚表：
 *   SCK=GPIO12 MISO=GPIO13 MOSI=GPIO11 CS=GPIO10 RST=GPIO9 DIO0=GPIO8
 *
 * 收帧 → loracanary_frame 镜像解析（magic/CRC/定长全校验，坏帧丢弃计数）→
 * 上行 JSON（USB 串口；WiFi 可用时同发 MQTT topic loracanary/<node_id>）：
 *   ENV(type=0x01, v1 兼容)： {"node_id":1,"t":26.3,"h":55.0,"p":1013.2,"rssi":-87}
 *   GEO(type=0x03, v1.5)   ： {"node_id":1,"t":26.3,"h":55.0,"p":1013.2,
 *        "lat":39.9042,"lng":116.4074,"alt":52,"sat":8,"gps_fix":true,"rssi":-87}
 *   sat=0 → gps_fix=false 照常上行（工单 AB-04 第 2 条，不丢帧）。
 *
 * 降级（诚实标注）：WiFi 连不上 → 仅串口上行不崩溃（v1 AA-03 契约延续）；
 * 无 LLM 调用；JSON/MQTT 只在网关→主机段（LoRa 链路二进制帧纪律）。
 *
 * 构建：arduino-cli compile --fqbn esp32:esp32:esp32s3 loracanary_gateway_s3
 * Python 镜像（同语义）：tools/loracanary_gateway.py（pytest V-xx 覆盖）
 */
#include <Arduino.h>
#include <SPI.h>

#include <PubSubClient.h>
#include <RadioLib.h>
#include <WiFi.h>

#include "loracanary_frame.h"

// ---- 网关参数 ----
#define WIFI_SSID  ""   // 空 = 不启用 MQTT，仅串口上行（诚实降级，串口足够 v1）
#define WIFI_PASS  ""
#define MQTT_HOST  ""   // 路由器/主机 broker 地址
#define MQTT_PORT  1883

// SX1278（v1 S3 接线表）
#define PIN_LORA_MOSI  11
#define PIN_LORA_MISO  13
#define PIN_LORA_SCK   12
#define PIN_LORA_CS    10
#define PIN_LORA_RST   9
#define PIN_LORA_DIO0  8

// ---- 状态 ----
static SX1278 s_radio = new Module(PIN_LORA_CS, PIN_LORA_DIO0, PIN_LORA_RST,
                                   RADIOLIB_NC);
static WiFiClient s_wifi;
static PubSubClient s_mqtt(s_wifi);
static bool s_mqtt_ok = false;
static uint32_t s_rx_count = 0;             // 收到合法帧数
static uint32_t s_bad_count = 0;            // 坏帧丢弃数（v1 第七节第 4 例契约）
static int32_t s_last_seq_by_node[33] = {0};  // seq 乱序/重复检测（v1 第 6 例），-1 = 未见首帧
static uint8_t s_rx_buf[LC_MAX_FRAME];

static void logEvent(const char *event, long v) {
  Serial.printf("{\"src\":\"gw\",\"event\":\"%s\",\"v\":%ld}\n", event, v);
}

static void mqttReconnect() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }
  s_mqtt_ok = s_mqtt.connect("loracanary-gw");
  if (!s_mqtt_ok) {
    logEvent("mqtt_fail_serial_only", 0);  // broker 不可达 → 仍走串口，不阻塞收帧
  }
}

static void wifiInit() {
  if (WIFI_SSID[0] == '\0') {
    logEvent("wifi_disabled_serial_only", 0);  // 未配置 → 仅串口（显式标注）
    return;
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
    delay(100);
  }
  if (WiFi.status() == WL_CONNECTED) {
    s_mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqttReconnect();
  } else {
    logEvent("wifi_fail_serial_only", 0);  // 断 WiFi 不崩（AA-03 契约）
  }
}

// 上行一条 JSON（串口必发；MQTT 可用则同发，topic 照 v1：loracanary/<node_id>）
static void uplink(const char *json, uint8_t node_id) {
  Serial.println(json);
  if (s_mqtt_ok) {
    char topic[32];
    snprintf(topic, sizeof(topic), "loracanary/%u", node_id);
    s_mqtt.publish(topic, json);
  }
}

// seq 乱序/重复检测：只记日志，不丢帧不崩溃（v1 SPEC 第七节第 6 例）
static void seqCheckAndEmit(const lc_frame_t *f, const char *json) {
  int32_t last = s_last_seq_by_node[f->node_id];
  if (last >= 0 && f->seq != (uint8_t)((last + 1) & 0xFF)) {
    logEvent("seq_gap", (last << 8) | f->seq);  // 高 24 位旧 seq，低 8 位新 seq
  }
  s_last_seq_by_node[f->node_id] = f->seq;
  uplink(json, f->node_id);
}

static void handleFrame(const uint8_t *buf, size_t n, float rssi) {
  lc_frame_t f;
  if (lc_decode_frame(buf, n, &f) != 1) {
    s_bad_count++;
    logEvent("bad_frame", (long)s_bad_count);  // 坏帧贞洁：丢弃并计数（v1 第 4 例）
    return;
  }
  s_rx_count++;

  char json[256];
  if (f.type == LC_TYPE_ENV) {
    snprintf(json, sizeof(json),
             "{\"node_id\":%u,\"t\":%.2f,\"h\":%.1f,\"p\":%.2f,\"rssi\":%.1f}",
             f.node_id, (double)f.env.t, (double)f.env.h, (double)f.env.p,
             (double)rssi);
    seqCheckAndEmit(&f, json);
    return;
  }
  if (f.type == LC_TYPE_GEO) {
    // v1.5 GEO 上行（工单 AB-04 第 1 条，字段与示例逐项一致）
    snprintf(json, sizeof(json),
             "{\"node_id\":%u,\"t\":%.2f,\"h\":%.1f,\"p\":%.2f,"
             "\"lat\":%.7f,\"lng\":%.7f,\"alt\":%d,\"sat\":%u,\"gps_fix\":%s,"
             "\"rssi\":%.1f}",
             f.node_id, (double)f.geo.t, (double)f.geo.h, (double)f.geo.p,
             f.geo.lat, f.geo.lng, f.geo.alt, f.geo.sat,
             f.geo.gps_fix ? "true" : "false", (double)rssi);
    seqCheckAndEmit(&f, json);
    return;
  }
  // HEARTBEAT/ACK/ERR：不产生数据上行 JSON（事件行标注，串口仍可读）
  if (f.type == LC_TYPE_HEARTBEAT) {
    Serial.printf("{\"src\":\"gw\",\"event\":\"heartbeat\",\"node_id\":%u,"
                  "\"seq\":%u,\"rssi\":%.1f}\n",
                  f.node_id, f.seq, (double)rssi);
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  for (int i = 0; i < 33; i++) {
    s_last_seq_by_node[i] = -1;
  }

  SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_CS);
  int16_t st = s_radio.begin(433.0, 125.0, 7, 5);  // 与节点同参数
  if (st == RADIOLIB_ERR_NONE) {
    s_radio.startReceive();  // 连续接收
  }
  logEvent("radio_init", st);

  wifiInit();
  Serial.printf("{\"src\":\"gw\",\"event\":\"ready\",\"mqtt\":%s}\n",
                s_mqtt_ok ? "true" : "false");
}

void loop() {
  int16_t state = s_radio.readData(s_rx_buf, LC_MAX_FRAME);
  if (state == RADIOLIB_ERR_NONE) {
    float rssi = s_radio.getRSSI();
    handleFrame(s_rx_buf, s_radio.getPacketLength(false), rssi);
    s_radio.startReceive();
  } else if (state != RADIOLIB_ERR_RX_TIMEOUT) {
    s_radio.startReceive();  // 异常态恢复进接收（CRC 错帧 RadioLib 返回错码，
                             // 计数走 decode 校验层，这里只管恢复）
  }
  if (s_mqtt_ok && !s_mqtt.connected()) {
    mqttReconnect();
  }
  delay(1);
}
