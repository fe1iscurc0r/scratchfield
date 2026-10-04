/* dcp 帧协议 · C 实现（与 mcpserver/rf_brain/dcp/frame.py 逐字节兼容）。
 *
 * 参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。
 *
 * 帧格式：magic(2B) + type(1B) + seq(2B LE) + payload(N) + crc(2B LE)
 * 总长 = 7 + N，payload ≤ 42B，最大帧长 49B < 50B。
 * CRC-16 MODBUS（poly 0x8005 / init 0xFFFF / refin/refout true），
 * 覆盖 type+seq+payload（不含 magic）。标准向量 b"123456789" → 0x4B37。
 */
#ifndef DCP_FRAME_H
#define DCP_FRAME_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- 帧格式常量 ---- */
#define DCP_MAGIC_0         0xD0
#define DCP_MAGIC_1         0xCC
#define DCP_HEADER_LEN      5   /* magic2 + type1 + seq2 */
#define DCP_CRC_LEN         2
#define DCP_OVERHEAD        7   /* header5 + crc2 */
#define DCP_MAX_PAYLOAD     42  /* 帧长<50 上限：7+42=49 */
#define DCP_MAX_FRAME       49

/* ---- 消息类型 ---- */
enum dcp_msg_type {
    DCP_REPORT    = 0x01,
    DCP_COMMAND   = 0x02,
    DCP_ACK       = 0x03,
    DCP_HEARTBEAT = 0x04,
};

/* ---- 协议 / 电池枚举（与 types.py 一致） ---- */
enum dcp_protocol {
    DCP_PROTO_ACURITE_TOWER = 0,
    DCP_PROTO_ACURITE_515   = 1,
    DCP_PROTO_LACROSSE_BV2  = 2,
    DCP_PROTO_ACURITE_5N1   = 3,
    DCP_PROTO_ACURITE_ATLAS = 4,
    DCP_PROTO_UNKNOWN       = 255,
};

enum dcp_battery {
    DCP_BATTERY_OK  = 0,
    DCP_BATTERY_LOW = 1,
};

/* REPORT payload 定长 9B */
#define DCP_REPORT_PAYLOAD_LEN 9

/* REPORT 解析结果（与 parse_report_payload 的 dict 对应） */
typedef struct {
    float    temperature_c;   /* ×10 存 int16 */
    uint8_t  humidity_pct;
    uint8_t  battery;         /* dcp_battery */
    int8_t   rssi_dbm;
    uint8_t  channel;         /* ASCII */
    uint8_t  protocol;        /* dcp_protocol */
    uint16_t device_id;
} dcp_report_t;

/* CRC-16 MODBUS：标准向量 dcp_crc16_modbus("123456789", 9) == 0x4B37 */
uint16_t dcp_crc16_modbus(const uint8_t *data, size_t len);

/* 编码一帧 → out，返回帧长；payload 超长返回 0 */
size_t dcp_encode(uint8_t type, uint16_t seq,
                  const uint8_t *payload, size_t payload_len, uint8_t *out);

/* 解码一帧：成功返回 payload 长度（写 out_type/out_seq/out_payload），坏帧返回 -1 */
int dcp_decode(const uint8_t *frame, size_t frame_len,
               uint8_t *out_type, uint16_t *out_seq, uint8_t *out_payload);

/* 构造 REPORT payload（定长 9B）→ out，返回 9 */
size_t dcp_build_report_payload(float temperature_c, uint8_t humidity_pct,
                                uint8_t battery, int8_t rssi_dbm,
                                uint8_t channel, uint8_t protocol,
                                uint16_t device_id, uint8_t *out);

/* 解析 REPORT payload（定长 9B）→ out；长度不足返回 0 */
int dcp_parse_report_payload(const uint8_t *payload, size_t len, dcp_report_t *out);

#ifdef __cplusplus
}
#endif

#endif /* DCP_FRAME_H */
