/* AC-01 · SX1278 收包分类 demo（ESP32-S3）——无乘法特征提取 + 汉明最近原型分类
 *
 * 依据：firmware/mulfree/README.md + docs/SPEC-20 系列（LoRaCanary 生态）
 *
 * 【诚实降级标注】当前无 SX1278 真机/无真实收包数据：
 *   - 默认 MULFREE_DEMO_SX1278=0：使用内置 mock 包（黄金向量，合成数据，
 *     由 tools/gen_mulfree_assets.py 生成），演示 特征提取→分类→混淆统计→周期基准 全链路。
 *   - MULFREE_DEMO_SX1278=1：真机路径（RadioLib SX1278 收包 → 同一特征/分类管线）。
 *     硬件接线后才可启用，本路径代码未经实物验证（诚实标注）。
 *
 * 热路径（mulfree::packet_features / classify）无乘法指令——验收见
 * tools/objdump_mulfree_check.py；本文件内的基准计算（cycles 换算等）
 * 属于报告代码，允许乘法，不在验收范围。
 *
 * 编译：arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/mulfree/mulfree_packet_demo
 */
#include <Arduino.h>

#define MULFREE_DEMO_SX1278 0   /* 真机收包开关：0=mock（默认），1=SX1278（需接线） */

#if MULFREE_DEMO_SX1278
#include <RadioLib.h>           /* 依赖：RadioLib 7.x（见 README 依赖锁表） */
/* 引脚按 SPEC-20 S3 节点约定，接线后按实板调整： */
#define PIN_LORA_CS   10
#define PIN_LORA_RST   9
#define PIN_LORA_DIO0  8
SX1278 radio = new Module(PIN_LORA_CS, PIN_LORA_DIO0, PIN_LORA_RST);
static int16_t lora_rx(uint8_t *buf, size_t cap, size_t *out_len) {
  size_t n = 0;
  int16_t st = radio.readData(buf, cap);   /* 收到的帧字节（≤120B） */
  if (st == RADIOLIB_ERR_NONE) {
    n = radio.getPacketLength(false);
    if (n > cap) n = cap;
  }
  *out_len = n;
  return st;
}
#endif

#include "mulfree_features.h"
#include "mulfree_prototypes.h"
#include "mulfree_float_ref.h"

static const char *kClassNames[3] = {"NORMAL", "NOISE", "BAD_FRAME"};

/* 报告辅助：hex 字节流（避免乘法相关的顾虑仅限特征热路径，此处随意） */
static void print_hex(const uint8_t *b, int n) {
  for (int i = 0; i < n; i++) {
    if (b[i] < 0x10) Serial.print('0');
    Serial.print(b[i], HEX);
  }
}

static uint8_t hexval(char c) {
  if (c >= '0' && c <= '9') return (uint8_t)(c - '0');
  if (c >= 'A' && c <= 'F') return (uint8_t)(c - 'A' + 10);
  return (uint8_t)(c - 'a' + 10);
}

static int hex2bin(const char *hex, uint8_t *out, int cap) {
  int n = 0;
  for (int i = 0; hex[i] && hex[i + 1] && n < cap; i += 2) {
    out[n++] = (uint8_t)((hexval(hex[i]) << 4) | hexval(hex[i + 1]));
  }
  return n;
}

static void run_demo_once() {
  uint8_t buf[256];
  int conf[3][3] = {{0}};

  /* ---- 1. 逐包：特征提取 → 分类 → 逐包 JSON 行（mock 数据） ---- */
  for (int i = 0; i < MULFREE_GOLDEN_N; i++) {
    int n = hex2bin(MULFREE_GOLDEN[i].hex, buf, sizeof(buf));
    uint64_t bits = mulfree::packet_features(buf, (size_t)n);
    int pred = mulfree::classify(bits);
    conf[MULFREE_GOLDEN[i].cls][pred]++;
    Serial.printf("{\"demo_pkt\":%d,\"mock\":true,\"len\":%d,\"hex\":\"",
                  i, n);
    print_hex(buf, n < 12 ? n : 12);
    Serial.printf("\",\"bits\":\"%llX\",\"cls_expect\":%d,\"cls_pred\":%d,"
                  "\"cls_name\":\"%s\"}\n",
                  (unsigned long long)bits, MULFREE_GOLDEN[i].cls, pred,
                  kClassNames[pred]);
  }

  /* ---- 2. 混淆矩阵（黄金向量 3 类 × 各 4 条） ---- */
  Serial.printf("{\"confusion_row_major\":[[%d,%d,%d],[%d,%d,%d],[%d,%d,%d]],"
                "\"note\":\"mock 黄金向量, 行=真 列=预测\"}\n",
                conf[0][0], conf[0][1], conf[0][2],
                conf[1][0], conf[1][1], conf[1][2],
                conf[2][0], conf[2][1], conf[2][2]);

  /* ---- 3. 周期基准：无乘法规 vs 乘法规（esp_timer 实测，需真机才有数） ----
   * 真机烧录后此行输出 cycles/样本；Wokwi/模拟器数值不采信。 */
  const int kIters = 2000;
  int n0 = hex2bin(MULFREE_GOLDEN[0].hex, buf, sizeof(buf));
  volatile uint64_t sink = 0;                 /* 防优化删除 */
  int64_t t0 = esp_timer_get_time();
  for (int i = 0; i < kIters; i++) {
    sink ^= mulfree::packet_features(buf, (size_t)n0);
  }
  int64_t t1 = esp_timer_get_time();
  for (int i = 0; i < kIters; i++) {
    sink ^= float_packet_features(buf, (size_t)n0);
  }
  int64_t t2 = esp_timer_get_time();
  int64_t us_mulfree = (t1 - t0) * 1000 / kIters;   /* ns/样本（报告代码） */
  int64_t us_float = (t2 - t1) * 1000 / kIters;
  Serial.printf("{\"bench\":{\"ns_per_sample_mulfree\":%lld,"
                "\"ns_per_sample_float\":%lld,\"iters\":%d,"
                "\"cpu_mhz\":240,\"note\":\"esp_timer 实测, 需真机\"}}\n",
                (long long)us_mulfree, (long long)us_float, kIters);
  Serial.printf("{\"bench_sink\":%llu}\n", (unsigned long long)(sink & 1));
}

void setup() {
  Serial.begin(115200);
  delay(200);

#if MULFREE_DEMO_SX1278
  /* 真机路径：初始化 433MHz SF7/BW125（SPEC-20 铁律：≤100mW，13dBm） */
  int16_t st = radio.begin(433.0, 125.0, 7, 5, RADIOLIB_SX127X_TX_POWER_13DBM);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("{\"event\":\"lora_init_fail\",\"code\":%d}\n", st);
  }
#endif

  Serial.printf("{\"boot\":\"mulfree_packet_demo\",\"mode\":\"%s\"}\n",
                MULFREE_DEMO_SX1278 ? "sx1278_real" : "mock_golden");
  run_demo_once();
}

void loop() {
#if MULFREE_DEMO_SX1278
  /* 真机收包 → 特征 → 分类（代码路径未经实物验证，接线后启用） */
  uint8_t rbuf[128];
  size_t rn = 0;
  if (lora_rx(rbuf, sizeof(rbuf), &rn) == RADIOLIB_ERR_NONE && rn > 0) {
    uint64_t bits = mulfree::packet_features(rbuf, rn);
    int pred = mulfree::classify(bits);
    Serial.printf("{\"rx_pkt\":true,\"len\":%d,\"cls\":\"%s\",\"bits\":\"%llX\"}\n",
                  (int)rn, kClassNames[pred], (unsigned long long)bits);
  }
  delay(50);
#else
  delay(10000);   /* mock 模式：10s 重跑一轮，便于串口观察 */
  run_demo_once();
#endif
}
