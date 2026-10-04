/* LoRaCanary 帧协议 · C++ 镜像（ESP32 侧用，与 tools/lora_frame.py 逐字节兼容）。
 *
 * 依据 docs/SPEC-20-v1.5-LoRaCanary扩增-GPS睡眠C3-总纲.md 第二节 + SPEC-20 v1 第二节。
 * 参考仓库内 dcp_frame.h（PAPA 线产物）的 C 接口风格独立实现，不整段复制。
 *
 * 帧格式：magic(2B) + type(1B) + seq(1B) + node_id(1B) + payload(N) + crc16(2B LE)
 * 总长 = 7 + N，payload ≤ 120B
 *
 * 消息类型 type：
 *   0x01 = ENV（环境数据）   payload 定长 7B   —— v1 原样保留
 *   0x02 = HEARTBEAT（心跳） payload 0B
 *   0x03 = GEO（定位+环境）  payload 定长 18B  —— v1.5 新增（AB-01）
 *   0xFE = ACK（确认）       payload 0B
 *   0xFF = ERR（错误）       payload 0B
 *
 * GEO payload（18B，偏移固定，Python/C++ 逐字节一致）：
 *   [0-1]  t   int16 LE ×100（0.01℃）
 *   [2]    h   uint8（湿度 %）
 *   [3-6]  p   uint32 LE ×100（0.01hPa）
 *   [7-10] lat int32 LE ×1e7（度）
 *   [11-14]lng int32 LE ×1e7（度）
 *   [15-16]alt int16 LE（米，有符号）
 *   [17]   sat uint8（卫星数，0 = 无定位）
 *   勘误：工单「16B/总帧 23B」系算术笔误，逐字段合计 18B（总帧 25B），
 *   详见 SPEC-20 v1.5 第二节与 lora_frame.py 头注。
 *   降级：sat=0 时 build 强制 lat/lng/alt=0（无定位不报假坐标）。
 *
 * CRC-16 MODBUS（poly 0x8005 / init 0xFFFF / refin+refout），覆盖
 * type+seq+node_id+payload（不含 magic）。标准向量 "123456789" → 0x4B37。
 *
 * decode 对坏帧（magic 错/CRC 错/type 未知/定长不符/超长）一律返回 0，不抛不崩。
 */
#ifndef LORACANARY_FRAME_H
#define LORACANARY_FRAME_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- 帧格式常量（与 lora_frame.py 同名常量对应） ---- */
#define LC_MAGIC_0          0xD0
#define LC_MAGIC_1          0xCC
#define LC_HEADER_LEN       5    /* magic2 + type1 + seq1 + node_id1 */
#define LC_CRC_LEN          2
#define LC_OVERHEAD         7    /* header5 + crc2 */
#define LC_MAX_PAYLOAD      120  /* LoRa 单包载荷上限（铁律） */
#define LC_MAX_FRAME        (LC_OVERHEAD + LC_MAX_PAYLOAD)  /* 127 */

#define LC_ENV_PAYLOAD_LEN  7    /* t(2) + h(1) + p(4) */
#define LC_GEO_PAYLOAD_LEN  18   /* t(2)+h(1)+p(4)+lat(4)+lng(4)+alt(2)+sat(1) */
#define LC_GEO_FRAME_LEN    (LC_OVERHEAD + LC_GEO_PAYLOAD_LEN)  /* 25 */

/* ---- 消息类型 ---- */
enum lc_msg_type {
    LC_TYPE_ENV       = 0x01,
    LC_TYPE_HEARTBEAT = 0x02,
    LC_TYPE_GEO       = 0x03,   /* v1.5 GEO */
    LC_TYPE_ACK       = 0xFE,
    LC_TYPE_ERR       = 0xFF,
};

/* ---- 解析结果结构 ---- */
typedef struct {
    float   t;        /* ℃ */
    uint8_t h;        /* % */
    float   p;        /* hPa */
} lc_env_t;

typedef struct {
    float   t;        /* ℃ */
    uint8_t h;        /* % */
    float   p;        /* hPa */
    double  lat;      /* 度（×1e7 定点还原） */
    double  lng;      /* 度 */
    int16_t alt;      /* 米 */
    uint8_t sat;      /* 卫星数 */
    uint8_t gps_fix;  /* 1 = sat>0 */
} lc_geo_t;

typedef struct {
    uint8_t  type;
    uint8_t  seq;
    uint8_t  node_id;
    uint8_t  payload[LC_MAX_PAYLOAD];
    size_t   payload_len;
    lc_env_t env;  /* type==LC_TYPE_ENV 时有效 */
    lc_geo_t geo;  /* type==LC_TYPE_GEO 时有效 */
} lc_frame_t;

/* CRC-16 MODBUS（查表法）。标准向量 "123456789" → 0x4B37。 */
uint16_t loracanary_crc16(const uint8_t *data, size_t len);

/* 构造 7B ENV payload → out（容量 ≥ 7），返回 7。 */
size_t lc_build_env_payload(float t, uint8_t h, float p, uint8_t *out);

/* 构造 18B GEO payload → out（容量 ≥ 18），返回 18。
 * sat==0 时强制 lat/lng/alt=0（诚实降级，与 Python encode 一致）。 */
size_t lc_build_geo_payload(float t, uint8_t h, float p,
                            double lat, double lng, int16_t alt, uint8_t sat,
                            uint8_t *out);

/* 构造整帧 → out（容量 ≥ 7+payload_len，且 payload_len ≤ 120）。
 * 成功返回总帧长；payload 超长返回 0（拒绝，不截断）。 */
size_t lc_build_frame(uint8_t type, uint8_t seq, uint8_t node_id,
                      const uint8_t *payload, size_t payload_len,
                      uint8_t *out, size_t out_cap);

/* 解析 ENV payload（长度须 == 7）。成功返回 1，失败返回 0。 */
int lc_parse_env_payload(const uint8_t *payload, size_t len, lc_env_t *out);

/* 解析 GEO payload（长度须 == 18）。成功返回 1，失败返回 0。 */
int lc_parse_geo_payload(const uint8_t *payload, size_t len, lc_geo_t *out);

/* 解码整帧（校验 magic + CRC + type + 定长 + 超长）。成功返回 1 并填 *out，
 * 坏帧返回 0（不修改 out，不崩——坏帧贞洁，与 Python decode 返回 None 对应）。 */
int lc_decode_frame(const uint8_t *frame, size_t len, lc_frame_t *out);

#ifdef __cplusplus
}
#endif

#endif /* LORACANARY_FRAME_H */
