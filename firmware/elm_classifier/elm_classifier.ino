/* elm_classifier.ino — ESP32-S3 定点 ELM 分类器（OTA-ELM 轻量推理 01-02）。
 *
 * 功能：加载 elm_model.h 里的 int8 定点模型做实时分类；无信号源时用 mock 特征
 * 循环演示三类输出。串口 NDJSON 行（115200-8-N-1），与 sentinel 输出风格一致。
 *
 * 本线只做「唤醒即分类」的推理层，不实现唤醒（见 sleep_epoch/lowpower）与
 * SX1278 收包/特征提取，仅留接口注释（见 elm_on_features / elm_on_wake_classify）。
 *
 * 接线：无需射频即可跑 mock 演示；接 SX1278 时复用 firmware/README.md §2 引脚表
 * （SPI: SCK=12 MISO=13 MOSI=11 NSS=10 RESET=9 DIO0=8，433MHz ≤100mW）。
 */

#include <Arduino.h>
#include "elm_infer.h"

/* mock 特征：三类信号中心点（与训练数据同源，见 tools/elm_train.py make_demo_dataset）。
 * 期望分类 A/B/C，PC 端定点模型验证置信度依次 583/602/572 千分比。 */
static const double MOCK_FEATURES[3][ELM_N_FEATURES] = {
    {-85.0, 6.0, 0.8,  3.2,  0.15, 0.28, 14.0, 0.08},  /* A: SF7/BW125 型 */
    {-92.0, 4.0, 0.2,  2.8,  0.00, 0.12,  7.0, 0.22},  /* B: SF9/BW125 型 */
    {-98.0, 2.5, -0.3, 2.5, -0.10, 0.05,  0.0, 0.50},  /* C: SF12/BW125 型 */
};

/* 特征输入接口：SX1278 收到信号后提取物理量特征 → 分类。
 * 特征定义必须与训练严格对齐（8 维：env_mean/env_std/env_skew/env_kurt/
 * spec_peak_pos/spec_bw/snr_db/rise_time，见 README §特征工程）。
 * 接入点（本线不实现）：
 *   - 包络统计：SX1278 RSSI/包络采样 → env_mean/std/skew/kurt + rise_time
 *   - 谱形统计：FFT 幅度谱 → spec_peak_pos/spec_bw
 *   - SNR：SX1278 RegPktSnrValue 或底噪估计 → snr_db
 * 提取完成后调用本函数即可。 */
void elm_on_features(const double feats[ELM_N_FEATURES]) {
    int8_t x_q[ELM_N_FEATURES];
    elm_quantize_input(feats, x_q);
    elm_result_t r;
    elm_run(x_q, &r);

    Serial.print("{\"src\":\"elm\",\"type\":\"class\",\"clazz\":\"");
    Serial.print(ELM_CLASS_NAMES[r.class_index]);
    Serial.print("\",\"conf_permille\":");
    Serial.print(r.confidence_permille);
    Serial.print(",\"probs\":[");
    for (int k = 0; k < ELM_N_OUTPUTS; k++) {
        if (k) Serial.print(',');
        Serial.print(r.prob_permille[k]);
    }
    Serial.println("]}");
}

/* 唤醒即分类 hook（round9 MagPie 衔接）。
 * 本线不实现唤醒：LoRa 节点被唤醒后，由上层（sleep_epoch/lowpower 唤醒源）
 * 在提取到信号特征后调用 elm_on_features()。此处仅演示占位，真实唤醒流程
 * 由 sleep_epoch 线负责，本函数不在 loop 中主动调用。 */
void elm_on_wake_classify() {
    Serial.println("{\"src\":\"elm\",\"type\":\"wake_hook\",\"note\":\"round9 MagPie 唤醒即分类接口，本线未实现唤醒\"}");
}

void setup() {
    Serial.begin(115200);
    delay(100);
    Serial.print("{\"src\":\"elm\",\"type\":\"boot\",\"firmware\":\"elm-classifier-v1.0.0\",");
    Serial.print("\"model\":\"OTA-ELM int8\",\"n_hidden\":");
    Serial.print(ELM_N_HIDDEN);
    Serial.println("}");
}

void loop() {
    static int idx = 0;
    /* 无信号源 mock 演示：A→B→C 循环分类。接真实 SX1278 特征流后替换为
       elm_on_features(提取到的特征) 即可。 */
    elm_on_features(MOCK_FEATURES[idx]);
    idx = (idx + 1) % 3;
    delay(2000);
}
