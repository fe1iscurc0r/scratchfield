/* dcp 帧协议 C 侧单测（Arduino 断言宏，编解码往返 ≥5 用例）。
 *
 * 【未编译验证】云服无 ESP32 工具链，本文件未经编译；逻辑与
 * mcpserver/rf_brain/tests/test_dcp.py 的 14 个用例逐一对应，
 * 真机侧可经 PlatformIO test 或 Arduino 串口调用 dcp_frame_selftest() 验证。
 *
 * 参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。
 */
#include <stdio.h>
#include <string.h>

#include "dcp_frame.h"

static int _checks = 0;
static int _failures = 0;

#define CHECK(cond)                                                     \
    do {                                                                \
        _checks++;                                                      \
        if (!(cond)) {                                                  \
            printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond);      \
            _failures++;                                                \
        }                                                               \
    } while (0)

int dcp_frame_selftest(void) {
    uint8_t payload[9];
    uint8_t out_payload[9];
    uint8_t frame[DCP_MAX_FRAME];
    uint8_t bad[DCP_MAX_FRAME];
    uint8_t type;
    uint16_t seq;
    int plen;
    size_t flen;
    dcp_report_t rep;

    /* 1. CRC-16 MODBUS 标准向量 */
    const uint8_t vec[] = "123456789";
    CHECK(dcp_crc16_modbus(vec, 9) == 0x4B37);

    /* 2. REPORT 编解码往返 + 帧长 <50 */
    dcp_build_report_payload(25.0f, 50, DCP_BATTERY_OK, -85, 'C',
                             DCP_PROTO_ACURITE_TOWER, 4660, payload);
    flen = dcp_encode(DCP_REPORT, 1, payload, 9, frame);
    CHECK(flen == 16);
    CHECK(flen < 50);

    plen = dcp_decode(frame, flen, &type, &seq, out_payload);
    CHECK(plen == 9);
    CHECK(type == DCP_REPORT);
    CHECK(seq == 1);
    CHECK(memcmp(payload, out_payload, 9) == 0);

    /* 3. REPORT 字段解析往返 */
    CHECK(dcp_parse_report_payload(out_payload, 9, &rep) == 1);
    CHECK(rep.temperature_c == 25.0f);
    CHECK(rep.humidity_pct == 50);
    CHECK(rep.battery == DCP_BATTERY_OK);
    CHECK(rep.rssi_dbm == -85);
    CHECK(rep.channel == 'C');
    CHECK(rep.protocol == DCP_PROTO_ACURITE_TOWER);
    CHECK(rep.device_id == 4660);

    /* 4. CRC 错帧丢弃 */
    memcpy(bad, frame, flen);
    bad[5] ^= 0xFF;
    CHECK(dcp_decode(bad, flen, &type, &seq, out_payload) == -1);

    /* 5. magic 错帧丢弃 */
    memcpy(bad, frame, flen);
    bad[0] = 0x4D;
    bad[1] = 0x52;
    CHECK(dcp_decode(bad, flen, &type, &seq, out_payload) == -1);

    /* 6. 负温度 + LOW 电池 + 负 RSSI 往返 */
    uint8_t p2[9];
    dcp_build_report_payload(-12.5f, 88, DCP_BATTERY_LOW, -110, 'A',
                             DCP_PROTO_ACURITE_515, 1, p2);
    CHECK(dcp_parse_report_payload(p2, 9, &rep) == 1);
    CHECK(rep.temperature_c == -12.5f);
    CHECK(rep.battery == DCP_BATTERY_LOW);
    CHECK(rep.rssi_dbm == -110);
    CHECK(rep.protocol == DCP_PROTO_ACURITE_515);

    /* 7. 坏帧边界：过短帧 / 非法 type */
    CHECK(dcp_decode(frame, 3, &type, &seq, out_payload) == -1);
    dcp_encode(0x05, 1, NULL, 0, bad);  /* 非法 type */
    CHECK(dcp_decode(bad, DCP_OVERHEAD, &type, &seq, out_payload) == -1);

    printf("dcp_frame_selftest: %d checks, %d failures\n", _checks, _failures);
    return _failures;
}
