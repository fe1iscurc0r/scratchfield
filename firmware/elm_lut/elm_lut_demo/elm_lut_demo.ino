/* AC-02 · OTA-ELM 查表推理 demo（ESP32-S3）——ELM 前向推理，tanh 查表激活
 *
 * 依据：firmware/elm_lut/README.md
 *
 * 【诚实降级标注】当前无真机/无真实收包数据：
 *   - 默认 mock 模式：使用内置黄金向量包（合成数据，tools/gen_elm_assets.py 生成），
 *     演示 特征提取→LUT 推理→对照 float 推理→混淆统计→周期基准 全链路。
 *   - 收包接入：把 SX1278 收到的帧字节流传入 elm_lut::packet_features_q7 +
 *     infer_lut 即可（见 mulfree_packet_demo 的真机路径说明，同一帧契约）。
 *
 * LUT 推理路径无浮点无 libm（整数 MAC + 查表）；float 路径仅作对照打印。
 * 基准换算（cycles = ns × MHz）属于报告代码，允许乘法。
 *
 * 编译：arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/elm_lut/elm_lut_demo
 */
#include <Arduino.h>
#include "elm_inference.h"
#include "elm_weights.h"

static const char *kClassNames[3] = {"NORMAL", "NOISE", "BAD_FRAME"};

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
  int conf_l[3][3] = {{0}};
  int agree = 0;

  /* ---- 1. 逐包：定点特征 → LUT 推理 + float 对照 → JSON 行（mock 数据） ---- */
  for (int i = 0; i < ELM_GOLDEN_N; i++) {
    int n = hex2bin(ELM_GOLDEN[i].hex, buf, sizeof(buf));
    int16_t x_q[8];
    double x_r[8];
    int32_t ll[3];
    double lf[3];
    elm_lut::packet_features_q7(buf, (size_t)n, x_q);
    elm_lut::packet_features_real(buf, (size_t)n, x_r);
    int pred_l = elm_lut::infer_lut(x_q, ll);
    int pred_f = elm_lut::infer_float(x_r, lf);
    conf_l[ELM_GOLDEN[i].cls][pred_l]++;
    agree += pred_l == pred_f;
    /* LUT logits 实数语义 = s/(2^8·127)；打印定点值，避免报告层引入换算噪声 */
    Serial.printf("{\"elm_pkt\":%d,\"mock\":true,\"len\":%d,"
                  "\"cls\":%d,\"pred_lut\":%d,\"cls_name\":\"%s\","
                  "\"lut_logits\":[%ld,%ld,%ld],"
                  "\"float_logits\":[%.3f,%.3f,%.3f],"
                  "\"lut_equals_float\":%s}\n",
                  i, n, ELM_GOLDEN[i].cls, pred_l, kClassNames[pred_l],
                  (long)ll[0], (long)ll[1], (long)ll[2], lf[0], lf[1], lf[2],
                  pred_l == pred_f ? "true" : "false");
  }

  /* ---- 2. 混淆矩阵 + 双路径一致性 ---- */
  Serial.printf("{\"confusion_row_major\":[[%d,%d,%d],[%d,%d,%d],[%d,%d,%d]],"
                "\"lut_float_agree\":%d,\"note\":\"mock 黄金向量\"}\n",
                conf_l[0][0], conf_l[0][1], conf_l[0][2],
                conf_l[1][0], conf_l[1][1], conf_l[1][2],
                conf_l[2][0], conf_l[2][1], conf_l[2][2], agree);

  /* ---- 3. 周期基准：LUT 推理 vs float 推理（esp_timer 实测，需真机） ---- */
  const int kIters = 5000;
  int n0 = hex2bin(ELM_GOLDEN[0].hex, buf, sizeof(buf));
  int16_t x_q0[8];
  double x_r0[8];
  int32_t llsink[3];
  double lfsink[3];
  elm_lut::packet_features_q7(buf, (size_t)n0, x_q0);
  elm_lut::packet_features_real(buf, (size_t)n0, x_r0);
  volatile uint32_t sink = 0;                    /* 防优化删除 */
  int64_t t0 = esp_timer_get_time();
  for (int i = 0; i < kIters; i++) {
    sink ^= (uint32_t)elm_lut::infer_lut(x_q0, llsink);
  }
  int64_t t1 = esp_timer_get_time();
  for (int i = 0; i < kIters; i++) {
    sink ^= (uint32_t)elm_lut::infer_float(x_r0, lfsink);
  }
  int64_t t2 = esp_timer_get_time();
  int64_t ns_lut = (t1 - t0) * 1000000 / kIters;
  int64_t ns_float = (t2 - t1) * 1000000 / kIters;
  Serial.printf("{\"bench\":{\"ns_per_infer_lut\":%lld,"
                "\"ns_per_infer_float\":%lld,\"iters\":%d,"
                "\"note\":\"esp_timer 实测, 需真机\"}}\n",
                (long long)ns_lut, (long long)ns_float, kIters);
  Serial.printf("{\"bench_sink\":%u}\n", (unsigned)sink);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("{\"boot\":\"elm_lut_demo\",\"mode\":\"mock_golden\"}");
  run_demo_once();
}

void loop() {
  delay(10000);   /* mock 模式：10s 重跑一轮，便于串口观察 */
  run_demo_once();
}
