/* dcp 帧协议 C 实现（与 dcp/frame.py 逐字节兼容）。
 * 参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。
 */
#include "dcp_frame.h"

#include <math.h>
#include <string.h>

/* CRC-16 MODBUS（refin/refout=true，逐位法，与 Python 查表法同值）。 */
uint16_t dcp_crc16_modbus(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

size_t dcp_encode(uint8_t type, uint16_t seq,
                  const uint8_t *payload, size_t payload_len, uint8_t *out) {
    if (payload_len > DCP_MAX_PAYLOAD) {
        return 0;
    }
    out[0] = DCP_MAGIC_0;
    out[1] = DCP_MAGIC_1;
    out[2] = type;
    out[3] = (uint8_t)(seq & 0xFF);
    out[4] = (uint8_t)((seq >> 8) & 0xFF);
    if (payload_len && payload) {
        memcpy(out + DCP_HEADER_LEN, payload, payload_len);
    }
    /* CRC 覆盖 type + seq + payload（out[2 .. 5+payload_len)），不含 magic */
    uint16_t crc = dcp_crc16_modbus(out + 2, 3 + payload_len);
    uint8_t *crc_pos = out + DCP_HEADER_LEN + payload_len;
    crc_pos[0] = (uint8_t)(crc & 0xFF);
    crc_pos[1] = (uint8_t)((crc >> 8) & 0xFF);
    return DCP_OVERHEAD + payload_len;
}

int dcp_decode(const uint8_t *frame, size_t frame_len,
               uint8_t *out_type, uint16_t *out_seq, uint8_t *out_payload) {
    if (!frame || frame_len < DCP_OVERHEAD) {
        return -1;
    }
    if (frame[0] != DCP_MAGIC_0 || frame[1] != DCP_MAGIC_1) {
        return -1;
    }
    uint8_t type = frame[2];
    if (type != DCP_REPORT && type != DCP_COMMAND &&
        type != DCP_ACK && type != DCP_HEARTBEAT) {
        return -1;
    }
    uint16_t seq = (uint16_t)(frame[3] | (frame[4] << 8));
    size_t payload_len = frame_len - DCP_OVERHEAD;
    uint16_t crc = dcp_crc16_modbus(frame + 2, 3 + payload_len);
    uint16_t crc_rx = (uint16_t)(frame[frame_len - 2] | (frame[frame_len - 1] << 8));
    if (crc != crc_rx) {
        return -1;
    }
    if (out_type) *out_type = type;
    if (out_seq) *out_seq = seq;
    if (out_payload && payload_len) {
        memcpy(out_payload, frame + DCP_HEADER_LEN, payload_len);
    }
    return (int)payload_len;
}

size_t dcp_build_report_payload(float temperature_c, uint8_t humidity_pct,
                                uint8_t battery, int8_t rssi_dbm,
                                uint8_t channel, uint8_t protocol,
                                uint16_t device_id, uint8_t *out) {
    int16_t temp = (int16_t)roundf(temperature_c * 10.0f);
    out[0] = (uint8_t)(temp & 0xFF);
    out[1] = (uint8_t)((temp >> 8) & 0xFF);
    out[2] = humidity_pct;
    out[3] = battery;
    out[4] = (uint8_t)rssi_dbm;
    out[5] = channel;
    out[6] = protocol;
    out[7] = (uint8_t)(device_id & 0xFF);
    out[8] = (uint8_t)((device_id >> 8) & 0xFF);
    return DCP_REPORT_PAYLOAD_LEN;
}

int dcp_parse_report_payload(const uint8_t *payload, size_t len, dcp_report_t *out) {
    if (!payload || len != DCP_REPORT_PAYLOAD_LEN || !out) {
        return 0;
    }
    int16_t temp = (int16_t)(payload[0] | (payload[1] << 8));
    out->temperature_c = (float)temp / 10.0f;
    out->humidity_pct = payload[2];
    out->battery = payload[3];
    out->rssi_dbm = (int8_t)payload[4];
    out->channel = (payload[5] >= 32 && payload[5] <= 126) ? payload[5] : 0;
    out->protocol = (payload[6] <= DCP_PROTO_ACURITE_ATLAS) ? payload[6] : DCP_PROTO_UNKNOWN;
    out->device_id = (uint16_t)(payload[7] | (payload[8] << 8));
    return 1;
}
