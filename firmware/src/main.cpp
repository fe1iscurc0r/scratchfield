// 哨兵网格 N-03 · ESP32-S3 + SX1278 边缘频谱哨兵固件
//
// 职责：SX1278 以 OOK 模式收 433.92MHz 传感器信号 → 测量脉冲宽度
//       → PWM 分类（500us=0 / 1000us=1）→ 重组成 bit → Acurite 解码
//       → USB-CDC 串口输出 NDJSON 行。
//
// 协议格式事实来源：公开 gist《Acurite Sensor Message Format》。
// rtl_433（GPL-2.0）仅作协议文档参照，本固件为独立实现，不复制其 C 代码。
//
// 诚实标注：本固件未经真机编译验证（云服无 ESP32 工具链）。接线 / 烧录 /
// 真机验证点见 firmware/README.md。SX1278 OOK 模式的脉冲测量依赖定时器
// 分辨率，真机需按实际脉冲宽度校准 _SHORT_US / _LONG_US 阈值。

#include <Arduino.h>
#include <RadioLib.h>

// ---------------- SX1278 引脚（SuperMini 默认接线，见 README） ----------------
#define PIN_NSS   10
#define PIN_DIO0  5
#define PIN_DIO1  6
#define PIN_RST   9
#define PIN_SCK   12
#define PIN_MISO  13
#define PIN_MOSI  11

// ---------------- 射频参数 ----------------
#define FREQ_MHZ       433.92
#define RX_BANDWIDTH   250.0      // kHz，够 500us PWM 脉冲边沿
#define BITRATE_KBPS   1.2        // kbps（兼容 Acurite 500us 脉冲）
#define SHORT_US       500        // PWM 短脉冲 = 0
#define LONG_US        1000       // PWM 长脉冲 = 1
#define PULSE_TOL      0.30       // 容差
#define MAX_BITS       64         // 最大 bit 数（Tower 56 / 515 48）

SX1278 radio = new Module(PIN_NSS, PIN_DIO0, PIN_RST, PIN_DIO1);

// ---------------- OOK 接收缓冲 ----------------
volatile uint32_t pulse_start_us = 0;
volatile uint16_t pulse_count = 0;
volatile uint16_t pulse_widths[MAX_BITS];

// DIO1 中断：SX1278 在 OOK 模式下 DIO1 触发 = 检测到载波边沿
// 记录脉冲宽度（用 micros() 粗测，真机按需换 ESP32 RMT 提高精度）
void IRAM_ATTR on_pulse() {
  uint32_t now = micros();
  if (pulse_start_us != 0 && pulse_count < MAX_BITS) {
    uint32_t w = now - pulse_start_us;
    pulse_widths[pulse_count++] = (uint16_t)(w > 65535 ? 65535 : w);
  }
  pulse_start_us = now;
}

// ---------------- PWM 分类 ----------------
int classify(uint16_t width_us) {
  uint32_t mid = (SHORT_US + LONG_US) / 2;
  if (width_us < SHORT_US * (1 - PULSE_TOL) || width_us > LONG_US * (1 + PULSE_TOL))
    return -1;  // 无效宽度
  return width_us < mid ? 0 : 1;
}

// ---------------- bit → byte ----------------
void bits_to_bytes(const int *bits, int nbits, uint8_t *out, int *nbytes) {
  int n = nbits;
  int pad = (8 - (n % 8)) % 8;
  int total = n + pad;
  *nbytes = total / 8;
  for (int i = 0; i < *nbytes; i++) {
    uint8_t v = 0;
    for (int j = 0; j < 8; j++) {
      int idx = i * 8 + j - pad;
      int b = (idx < 0) ? 0 : bits[idx];
      v = (v << 1) | b;
    }
    out[i] = v;
  }
}

// ---------------- 偶校验 ----------------
bool parity_ok(const uint8_t *b, int n) {
  if (n <= 3) return true;
  for (int i = 2; i < n - 1; i++) {
    int ones = __builtin_popcount(b[i]);
    if (ones % 2 != 0) return false;  // 偶校验
  }
  return true;
}

// ---------------- 校验和 ----------------
bool checksum_ok(const uint8_t *b, int n) {
  uint32_t sum = 0;
  for (int i = 0; i < n - 1; i++) sum += b[i];
  return (uint8_t)(sum & 0xFF) == b[n - 1];
}

// ---------------- Acurite 解码 → NDJSON 输出 ----------------
void decode_and_report(const uint8_t *b, int n) {
  if (!parity_ok(b, n)) return;
  if (n == 7 && (b[2] & 0x3F) == 0x04) {
    // Tower 592TXR 温湿度
    uint16_t id = ((b[0] & 0x3F) << 8) | b[1];
    uint8_t ch_code = (b[0] >> 6) & 0x03;
    const char *ch = ch_code == 0 ? "C" : ch_code == 2 ? "B" : ch_code == 3 ? "A" : "?";
    uint8_t hum = b[3] & 0x7F;
    uint16_t raw_t = ((b[4] & 0x0F) << 7) | (b[5] & 0x7F);
    float temp_c = (raw_t - 1000.0f) / 10.0f;
    const char *bat = (b[2] & 0x40) ? "OK" : "low";
    char buf[256];
    snprintf(buf, sizeof(buf),
             "{\"src\":\"sentinel\",\"protocol\":\"acurite-tower\",\"id\":%u,"
             "\"channel\":\"%s\",\"temperature_c\":%.1f,\"humidity_pct\":%u,"
             "\"battery\":\"%s\",\"crc_ok\":%s}\n",
             id, ch, temp_c, hum, bat, checksum_ok(b, n) ? "true" : "false");
    Serial.print(buf);
  } else if (n == 6 && ((b[2] & 0x3F) == 0x08 || (b[2] & 0x3F) == 0x09)) {
    // 515 冰箱/冷冻
    uint16_t id = ((b[0] & 0x3F) << 8) | b[1];
    const char *kind = (b[2] & 0x3F) == 0x08 ? "fridge" : "freezer";
    uint16_t raw_f = ((b[3] & 0x7F) << 7) | (b[4] & 0x7F);
    float temp_f = (raw_f - 1480.0f) / 10.0f;
    char buf[256];
    snprintf(buf, sizeof(buf),
             "{\"src\":\"sentinel\",\"protocol\":\"acurite-515\",\"kind\":\"%s\","
             "\"id\":%u,\"temperature_f\":%.1f,\"crc_ok\":%s}\n",
             kind, id, temp_f, checksum_ok(b, n) ? "true" : "false");
    Serial.print(buf);
  }
}

// ---------------- 串口命令 ----------------
void handle_command(const String &cmd) {
  if (cmd == "STATUS") {
    Serial.printf("{\"src\":\"sentinel\",\"cmd\":\"status\",\"freq_mhz\":%.2f,"
                  "\"bw_khz\":%.1f,\"bitrate_kbps\":%.1f}\n",
                  FREQ_MHZ, RX_BANDWIDTH, BITRATE_KBPS);
  } else if (cmd == "RESET") {
    pulse_count = 0;
    pulse_start_us = 0;
    Serial.print("{\"src\":\"sentinel\",\"cmd\":\"reset\",\"ok\":true}\n");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  int st = radio.beginFSK(FREQ_MHZ, BITRATE_KBPS, 0.0f, RX_BANDWIDTH);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("{\"src\":\"sentinel\",\"error\":\"radio init fail %d\"}\n", st);
    while (1) delay(1000);
  }
  // 切到 OOK 模式（FSK 初始化后再设 OOK，RadioLib 6.x 用 setOOK）
  st = radio.setOOK(BITRATE_KBPS);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("{\"src\":\"sentinel\",\"error\":\"setOOK fail %d\"}\n", st);
    while (1) delay(1000);
  }
  radio.setRxBandwidth(RX_BANDWIDTH);

  pinMode(PIN_DIO1, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_DIO1), on_pulse, CHANGE);

  st = radio.receiveDirect();
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("{\"src\":\"sentinel\",\"error\":\"receiveDirect fail %d\"}\n", st);
  }
  Serial.print("{\"src\":\"sentinel\",\"ready\":true}\n");
}

void loop() {
  // 串口命令
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    handle_command(cmd);
  }

  // 收到完整脉冲序列（帧结束 = 静默一段时间）后解码
  if (pulse_count >= 48) {
    noInterrupts();
    int bits[MAX_BITS];
    int valid = 1;
    for (int i = 0; i < pulse_count && i < MAX_BITS; i++) {
      bits[i] = classify(pulse_widths[i]);
      if (bits[i] == -1) valid = 0;
    }
    int nbits = pulse_count;
    pulse_count = 0;
    interrupts();

    if (!valid) return;
    uint8_t bytes[MAX_BITS / 8 + 1];
    int nbytes = 0;
    bits_to_bytes(bits, nbits, bytes, &nbytes);
    decode_and_report(bytes, nbytes);
  }
  delay(1);
}
