/* LoRaCanary 帧镜像 · C++ 自测（黄金向量法，与 tools/lora_frame.py 逐字节对照）。
 *
 * 黄金向量由 Python 侧生成（tools/test_lora_frame.py 同源输入），本文件断言
 * C++ 镜像产生/解析完全相同的字节——两镜像任何一侧改动导致不一致，这里即红。
 *
 * 构建运行（任意 g++ 主机）：
 *   g++ -Wall -Wextra -o loracanary_frame_test loracanary_frame.cpp loracanary_frame_test.cpp
 *   ./loracanary_frame_test          # 输出 PASS 行，返回 0
 * 交叉编译语法校验（本仓库工具链，无法在本机运行 riscv 二进制）：
 *   riscv32-esp-elf-g++ -fsyntax-only ...（见 firmware/loracanary/README）
 */
#include <stdio.h>
#include <string.h>

#include "loracanary_frame.h"

static int g_pass = 0;
static int g_fail = 0;

#define CHECK(cond, name)                                              \
    do {                                                               \
        if (cond) {                                                    \
            printf("PASS: %s\n", name);                                \
            g_pass++;                                                  \
        } else {                                                       \
            printf("FAIL: %s\n", name);                                \
            g_fail++;                                                  \
        }                                                              \
    } while (0)

static void hex2bin(const char *hex, uint8_t *out, size_t cap, size_t *len) {
    *len = 0;
    for (size_t i = 0; hex[i] && hex[i + 1] && *len < cap; i += 2) {
        unsigned v;
        sscanf(hex + i, "%2x", &v);
        out[(*len)++] = (uint8_t)v;
    }
}

int main(void) {
    /* ---- 1. CRC 标准向量 ---- */
    CHECK(loracanary_crc16((const uint8_t *)"123456789", 9) == 0x4B37,
          "CRC16 MODBUS 标准向量 123456789->0x4B37");

    /* ---- 2. 黄金向量：GEO 编码逐字节（Python encode(geo=...) 同源） ---- */
    {
        uint8_t payload[LC_GEO_PAYLOAD_LEN];
        size_t pn = lc_build_geo_payload(26.3f, 55, 1013.2f,
                                         39.9042, 116.4074, 52, 8, payload);
        uint8_t frame[LC_GEO_FRAME_LEN];
        size_t n = lc_build_frame(LC_TYPE_GEO, 0, 1, payload, pn,
                                  frame, sizeof(frame));
        const char *golden =
            "d0cc030001460a37c88b0100d0e5c817105c6245340008ab6a";
        uint8_t want[64];
        size_t want_len;
        hex2bin(golden, want, sizeof(want), &want_len);
        CHECK(n == want_len && memcmp(frame, want, want_len) == 0,
              "GEO 黄金向量逐字节一致(t=26.3 lat=39.9042 sat=8)");
    }

    /* ---- 3. 黄金向量：sat=0 降级（lat/lng/alt 清零） ---- */
    {
        uint8_t payload[LC_GEO_PAYLOAD_LEN];
        size_t pn = lc_build_geo_payload(-12.5f, 99, 870.5f,
                                         -33.865143, 151.2099, -15, 0, payload);
        uint8_t frame[64];
        size_t n = lc_build_frame(LC_TYPE_GEO, 200, 7, payload, pn,
                                  frame, sizeof(frame));
        const char *golden =
            "d0cc03c8071efb630a54010000000000000000000000008de0";
        uint8_t want[64];
        size_t want_len;
        hex2bin(golden, want, sizeof(want), &want_len);
        CHECK(n == want_len && memcmp(frame, want, want_len) == 0,
              "GEO sat=0 降级逐字节一致(lat/lng/alt=0)");
    }

    /* ---- 4. 黄金向量：v1 ENV 不受 v1.5 改动影响 ---- */
    {
        uint8_t payload[LC_ENV_PAYLOAD_LEN];
        size_t pn = lc_build_env_payload(26.3f, 55, 1013.2f, payload);
        uint8_t frame[64];
        size_t n = lc_build_frame(LC_TYPE_ENV, 42, 1, payload, pn,
                                  frame, sizeof(frame));
        const char *golden = "d0cc012a01460a37c88b01009a1f";
        uint8_t want[64];
        size_t want_len;
        hex2bin(golden, want, sizeof(want), &want_len);
        CHECK(n == want_len && memcmp(frame, want, want_len) == 0,
              "v1 ENV 黄金向量逐字节一致(向后兼容)");
    }

    /* ---- 5. GEO 解码往返 ---- */
    {
        uint8_t payload[LC_GEO_PAYLOAD_LEN];
        size_t pn = lc_build_geo_payload(26.3f, 55, 1013.2f,
                                         39.9042, 116.4074, 52, 8, payload);
        uint8_t frame[64];
        size_t n = lc_build_frame(LC_TYPE_GEO, 5, 2, payload, pn,
                                  frame, sizeof(frame));
        lc_frame_t out;
        CHECK(lc_decode_frame(frame, n, &out) == 1, "GEO 整帧解码成功");
        CHECK(out.geo.sat == 8 && out.geo.gps_fix == 1, "GEO sat/gps_fix 还原");
        double lat_err = out.geo.lat - 39.9042;
        double lng_err = out.geo.lng - 116.4074;
        if (lat_err < 0) lat_err = -lat_err;
        if (lng_err < 0) lng_err = -lng_err;
        CHECK(lat_err < 1e-6 && lng_err < 1e-6, "GEO lat/lng 误差 < 1e-6 度");
    }

    /* ---- 6. 坏帧贞洁（magic/CRC/type/定长/超长） ---- */
    {
        uint8_t frame[64];
        uint8_t payload[LC_GEO_PAYLOAD_LEN];
        (void)lc_build_geo_payload(26.3f, 55, 1013.2f, 0, 0, 0, 0, payload);
        size_t n = lc_build_frame(LC_TYPE_GEO, 0, 1, payload,
                                  LC_GEO_PAYLOAD_LEN, frame, sizeof(frame));
        lc_frame_t out;
        memset(&out, 0, sizeof(out));

        uint8_t bad[64];
        memcpy(bad, frame, n);
        bad[0] = 0x00;   /* magic 错 */
        CHECK(lc_decode_frame(bad, n, &out) == 0, "magic 错 → 拒绝");

        memcpy(bad, frame, n);
        bad[n - 1] ^= 0xFF;   /* CRC 错 */
        CHECK(lc_decode_frame(bad, n, &out) == 0, "CRC 错 → 拒绝");

        CHECK(lc_decode_frame(frame, n - 1, &out) == 0, "GEO payload 短 1B → 定长不符拒绝");

        uint8_t long_payload[LC_MAX_PAYLOAD + 1];
        memset(long_payload, 0, sizeof(long_payload));
        CHECK(lc_build_frame(LC_TYPE_HEARTBEAT, 0, 1, long_payload,
                             LC_MAX_PAYLOAD + 1, bad, sizeof(bad)) == 0,
              "payload 121B 超长 → 构造拒绝");

        memcpy(bad, frame, n);
        bad[2] = 0x04;   /* 未知 type */
        /* 重算 CRC 使其自洽，仅 type 非法 */
        uint16_t crc = loracanary_crc16(bad + 2, n - 4);
        bad[n - 2] = (uint8_t)(crc & 0xFF);
        bad[n - 1] = (uint8_t)(crc >> 8);
        CHECK(lc_decode_frame(bad, n, &out) == 0, "未知 type=0x04 → 拒绝");

        CHECK(lc_decode_frame(frame, 3, &out) == 0, "帧短于 overhead → 拒绝");
        CHECK(lc_decode_frame(NULL, n, &out) == 0, "空指针 → 拒绝不崩");
    }

    /* ---- 7. sat=0 解码不崩、gps_fix=0 ---- */
    {
        uint8_t payload[LC_GEO_PAYLOAD_LEN];
        (void)lc_build_geo_payload(-12.5f, 99, 870.5f, -33.865143, 151.2099, -15, 0, payload);
        uint8_t frame[64];
        size_t n = lc_build_frame(LC_TYPE_GEO, 1, 7, payload, LC_GEO_PAYLOAD_LEN,
                                  frame, sizeof(frame));
        lc_frame_t out;
        CHECK(lc_decode_frame(frame, n, &out) == 1 && out.geo.sat == 0 &&
              out.geo.gps_fix == 0 && out.geo.lat == 0.0 && out.geo.alt == 0,
              "sat=0 帧解码不崩且降级字段为 0");
    }

    printf("----\n合计: %d passed, %d failed\n", g_pass, g_fail);
    return g_fail == 0 ? 0 : 1;
}
