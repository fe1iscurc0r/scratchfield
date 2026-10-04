/* SX1278 LoRa 模式收发（dcp 帧）—— 固件侧骨架。
 *
 * 参考 dcp arXiv 2605.26159（MIT）独立实现；LoRa 模式用 RadioLib 库。
 * 注意：与 N 线 OOK 接收（SX1278 OOK 收 433MHz 传感器）不同，本单用
 * SX1278 的 LoRa 模式收发 dcp 二进制帧。
 *
 * 【未编译验证】云服无 ESP32 工具链，本文件未经 pio run 编译；RadioLib API
 * （SX1278 begin 签名 / transmit / receive）若与实际版本有差异，按编译错误微调。
 *
 * SPI 引脚沿用 firmware/README.md（N-03 接线图）：
 *   SCK=12 MISO=13 MOSI=11 NSS=10 RST=9 DIO0=5 DIO1=6
 */
#include <RadioLib.h>

#include "dcp_frame.h"

/* 引脚（与 N-03 接线图一致，可改后同步宏） */
#define LORA_NSS  10
#define LORA_DIO0 5
#define LORA_RST  9
#define LORA_DIO1 6

/* LoRa 参数（与 N-03 OOK 的 433.92MHz 同频段；LoRa 模式参数独立） */
#define LORA_FREQ       433.92f   /* MHz */
#define LORA_BW         125.0f    /* kHz */
#define LORA_SF         7         /* 扩频因子 7~12 */
#define LORA_CR         5         /* 编码率 4/5 */
#define LORA_SYNC_WORD  0x12      /* 私有网络同步字 */
#define LORA_POWER      17        /* dBm */

static SX1278 radio = new Module(LORA_NSS, LORA_DIO0, LORA_RST, LORA_DIO1);

/* 初始化 SX1278 LoRa 模式；成功返回 0，失败返回错误码 */
int dcp_lora_begin(void) {
    int state = radio.begin(LORA_FREQ, LORA_BW, LORA_SF, LORA_CR, LORA_SYNC_WORD, LORA_POWER);
    if (state == RADIOLIB_ERR_NONE) {
        /* 进入接收态，等待入帧 */
        radio.startReceive();
    }
    return state;
}

/* 发一帧 dcp（内部 encode + LoRa 发送）；成功返回 0 */
int dcp_lora_send(uint8_t type, uint16_t seq,
                  const uint8_t *payload, size_t payload_len) {
    uint8_t frame[DCP_MAX_FRAME];
    size_t frame_len = dcp_encode(type, seq, payload, payload_len, frame);
    if (frame_len == 0) {
        return -1;  /* payload 超长 */
    }
    int state = radio.transmit(frame, frame_len);
    if (state == RADIOLIB_ERR_NONE) {
        radio.startReceive();  /* 发完回到接收态 */
    }
    return state;
}

/* 收一帧 dcp（LoRa 接收 + decode）；成功返回 payload 长度，坏帧返回 -1。
 * 调用方须保证 out_payload 容量 ≥ DCP_MAX_PAYLOAD（42B）。 */
int dcp_lora_receive(uint8_t *out_type, uint16_t *out_seq, uint8_t *out_payload) {
    uint8_t frame[DCP_MAX_FRAME];
    size_t frame_len = radio.getPacketLength();
    if (frame_len == 0 || frame_len > DCP_MAX_FRAME) {
        return -1;
    }
    int state = radio.readData(frame, frame_len);
    if (state != RADIOLIB_ERR_NONE) {
        return -1;
    }
    return dcp_decode(frame, frame_len, out_type, out_seq, out_payload);
}
