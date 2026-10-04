/* LoRaCanary 帧协议 · C++ 镜像实现（与 tools/lora_frame.py 逐字节一致，契约见 .h）。
 *
 * 舍入约定：与 Python round() 在常规量程上一致（×100 / ×1e7 后四舍五入取整）；
 * 极端半值（如恰好 x.5 的二进制表示）Python 银行家舍入与 C lround 取远差异，
 * 实测数值（温度 ±0.01℃、经纬 1e-7°）不受影响。
 */
#include "loracanary_frame.h"

#include <math.h>

/* ---- CRC-16 MODBUS（查表法，与 lora_frame.py 同表） ---- */
static uint16_t lc_crc16_table[256];
static int lc_crc16_table_ready = 0;

static void lc_crc16_table_init(void) {
    if (lc_crc16_table_ready) {
        return;
    }
    for (int i = 0; i < 256; i++) {
        uint16_t c = (uint16_t)i;
        for (int b = 0; b < 8; b++) {
            c = (uint16_t)((c & 1) ? ((c >> 1) ^ 0xA001) : (c >> 1));
        }
        lc_crc16_table[i] = c;
    }
    lc_crc16_table_ready = 1;
}

uint16_t loracanary_crc16(const uint8_t *data, size_t len) {
    lc_crc16_table_init();
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc = (uint16_t)((crc >> 8) ^ lc_crc16_table[(crc ^ data[i]) & 0xFF]);
    }
    return crc;
}

/* ---- 定点写入小工具（显式小端，不依赖主机字节序） ---- */
static void lc_put_u16le(uint8_t *out, uint16_t v) {
    out[0] = (uint8_t)(v & 0xFF);
    out[1] = (uint8_t)(v >> 8);
}

static void lc_put_u32le(uint8_t *out, uint32_t v) {
    out[0] = (uint8_t)(v & 0xFF);
    out[1] = (uint8_t)((v >> 8) & 0xFF);
    out[2] = (uint8_t)((v >> 16) & 0xFF);
    out[3] = (uint8_t)((v >> 24) & 0xFF);
}

static uint16_t lc_get_u16le(const uint8_t *in) {
    return (uint16_t)(in[0] | ((uint16_t)in[1] << 8));
}

static uint32_t lc_get_u32le(const uint8_t *in) {
    return (uint32_t)in[0] | ((uint32_t)in[1] << 8) |
           ((uint32_t)in[2] << 16) | ((uint32_t)in[3] << 24);
}

/* 有符号搬运：小端读出后按补码还原（int16/int32 LE，等价 Python signed=True） */
static int16_t lc_get_i16le(const uint8_t *in) {
    return (int16_t)lc_get_u16le(in);
}

static int32_t lc_get_i32le(const uint8_t *in) {
    return (int32_t)lc_get_u32le(in);
}

/* ---- 范围检查 ---- */
static int lc_in_i16(long long v)  { return v >= -32768LL && v <= 32767LL; }
static int lc_in_i32(long long v) { return v >= -2147483648LL && v <= 2147483647LL; }

/* ---- payload 构造 ---- */
size_t lc_build_env_payload(float t, uint8_t h, float p, uint8_t *out) {
    if (out == NULL) {
        return 0;
    }
    long long t_raw = lroundf((double)t * 100.0);   /* 0.01℃ */
    long long p_raw = lroundf((double)p * 100.0);   /* 0.01hPa */
    if (!lc_in_i16(t_raw)) {
        return 0;   /* t 超出 int16(×100) */
    }
    if (p_raw < 0 || p_raw > 0xFFFFFFFFLL) {
        return 0;   /* p 超出 uint32(×100) */
    }
    lc_put_u16le(out, (uint16_t)(int16_t)t_raw);
    out[2] = h;
    lc_put_u32le(out + 3, (uint32_t)p_raw);
    return LC_ENV_PAYLOAD_LEN;
}

size_t lc_build_geo_payload(float t, uint8_t h, float p,
                            double lat, double lng, int16_t alt, uint8_t sat,
                            uint8_t *out) {
    if (out == NULL) {
        return 0;
    }
    long long t_raw = lroundf((double)t * 100.0);
    long long p_raw = lroundf((double)p * 100.0);
    if (!lc_in_i16(t_raw) || p_raw < 0 || p_raw > 0xFFFFFFFFLL) {
        return 0;
    }
    if (sat == 0) {
        /* 诚实降级：无定位不报假坐标（与 Python build_geo_payload 一致） */
        lat = 0.0;
        lng = 0.0;
        alt = 0;
    }
    long long lat_raw = lround(lat * 10000000.0);  /* ×1e7 */
    long long lng_raw = lround(lng * 10000000.0);
    if (!lc_in_i32(lat_raw) || !lc_in_i32(lng_raw)) {
        return 0;   /* 经纬度超出 int32(×1e7) */
    }
    lc_put_u16le(out, (uint16_t)(int16_t)t_raw);
    out[2] = h;
    lc_put_u32le(out + 3, (uint32_t)p_raw);
    lc_put_u32le(out + 7, (uint32_t)(int32_t)lat_raw);
    lc_put_u32le(out + 11, (uint32_t)(int32_t)lng_raw);
    out[15] = (uint8_t)((uint16_t)alt & 0xFF);
    out[16] = (uint8_t)(((uint16_t)alt >> 8) & 0xFF);
    out[17] = sat;
    return LC_GEO_PAYLOAD_LEN;
}

/* ---- 整帧构造 ---- */
size_t lc_build_frame(uint8_t type, uint8_t seq, uint8_t node_id,
                      const uint8_t *payload, size_t payload_len,
                      uint8_t *out, size_t out_cap) {
    if (out == NULL || payload_len > LC_MAX_PAYLOAD ||
        out_cap < LC_OVERHEAD + payload_len) {
        return 0;
    }
    out[0] = LC_MAGIC_0;
    out[1] = LC_MAGIC_1;
    out[2] = type;
    out[3] = seq;
    out[4] = node_id;
    if (payload_len > 0) {
        if (payload == NULL) {
            return 0;
        }
        for (size_t i = 0; i < payload_len; i++) {
            out[LC_HEADER_LEN + i] = payload[i];
        }
    }
    /* CRC 覆盖 type+seq+node_id+payload（不含 magic），小端存放 */
    uint16_t crc = loracanary_crc16(out + 2, 3 + payload_len);
    lc_put_u16le(out + LC_HEADER_LEN + payload_len, crc);
    return LC_OVERHEAD + payload_len;
}

/* ---- payload 解析 ---- */
int lc_parse_env_payload(const uint8_t *payload, size_t len, lc_env_t *out) {
    if (payload == NULL || out == NULL || len != LC_ENV_PAYLOAD_LEN) {
        return 0;
    }
    out->t = (float)lc_get_i16le(payload) / 100.0f;
    out->h = payload[2];
    out->p = (float)lc_get_u32le(payload + 3) / 100.0f;
    return 1;
}

int lc_parse_geo_payload(const uint8_t *payload, size_t len, lc_geo_t *out) {
    if (payload == NULL || out == NULL || len != LC_GEO_PAYLOAD_LEN) {
        return 0;
    }
    out->t = (float)lc_get_i16le(payload) / 100.0f;
    out->h = payload[2];
    out->p = (float)lc_get_u32le(payload + 3) / 100.0f;
    out->lat = (double)lc_get_i32le(payload + 7) / 10000000.0;
    out->lng = (double)lc_get_i32le(payload + 11) / 10000000.0;
    out->alt = lc_get_i16le(payload + 15);
    out->sat = payload[17];
    out->gps_fix = (payload[17] > 0) ? 1 : 0;
    return 1;
}

/* ---- 整帧解码（坏帧贞洁：任一校验失败返回 0） ---- */
int lc_decode_frame(const uint8_t *frame, size_t len, lc_frame_t *out) {
    if (frame == NULL || out == NULL || len < LC_OVERHEAD) {
        return 0;
    }
    if (frame[0] != LC_MAGIC_0 || frame[1] != LC_MAGIC_1) {
        return 0;   /* magic 错 */
    }
    size_t payload_len = len - LC_OVERHEAD;
    if (payload_len > LC_MAX_PAYLOAD) {
        return 0;   /* 超长 */
    }
    uint16_t crc_expect = (uint16_t)(frame[len - 2] | ((uint16_t)frame[len - 1] << 8));
    if (loracanary_crc16(frame + 2, payload_len + 3) != crc_expect) {
        return 0;   /* CRC 错 */
    }
    switch (frame[2]) {
        case LC_TYPE_ENV:
            if (payload_len != LC_ENV_PAYLOAD_LEN) return 0;
            break;
        case LC_TYPE_HEARTBEAT:
        case LC_TYPE_ACK:
        case LC_TYPE_ERR:
            if (payload_len != 0) return 0;
            break;
        case LC_TYPE_GEO:
            if (payload_len != LC_GEO_PAYLOAD_LEN) return 0;
            break;
        default:
            return 0;   /* 未知 type */
    }
    out->type = frame[2];
    out->seq = frame[3];
    out->node_id = frame[4];
    out->payload_len = payload_len;
    for (size_t i = 0; i < payload_len; i++) {
        out->payload[i] = frame[LC_HEADER_LEN + i];
    }
    if (frame[2] == LC_TYPE_ENV) {
        if (!lc_parse_env_payload(out->payload, payload_len, &out->env)) {
            return 0;
        }
    } else if (frame[2] == LC_TYPE_GEO) {
        if (!lc_parse_geo_payload(out->payload, payload_len, &out->geo)) {
            return 0;
        }
    }
    return 1;
}
