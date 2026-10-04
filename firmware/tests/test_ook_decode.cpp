// 边缘频谱哨兵 · OOK 解码核心主机单元测试
//
// 与 mcpserver/rf_brain/test_ook_decoders.py（N-02）逐用例对齐：
// 字段往返 + CRC 对/错两路 + 温度 0.1°C / 湿度精度 + 负温度有符号 12bit。
//
// 构建 & 运行（任意装 g++ 的机器）：
//   g++ -std=c++17 -Wall -Wextra -O2 \
//       -I ../sentinel \
//       test_ook_decode.cpp ../sentinel/ook_decode.cpp \
//       -o test_ook_decode && ./test_ook_decode
#include <cstdio>
#include <cmath>
#include <string>
#include <vector>

#include "ook_decode.h"

using sentinel::Frame;

static int g_checks = 0;
static int g_failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        ++g_checks;                                                          \
        if (!(cond)) {                                                       \
            ++g_failures;                                                    \
            std::fprintf(stderr, "FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); \
        }                                                                    \
    } while (0)

#define CHECK_FLOAT(a, b) CHECK(std::fabs((a) - (b)) < 0.0001f)

// --------------------------------------------------------------------------
// 帧合成（与 Python encode_* 同构，只产「逻辑 bit 流」，不产脉冲）
// --------------------------------------------------------------------------

static std::vector<int> acurite_bits(uint32_t id, int ch /*0=C 1=B 2=A*/,
                                     bool battery, float temp_c, int hum) {
    static const int CH_CODE[3] = {0b00, 0b10, 0b11};
    int bb[7] = {0};
    bb[0] = (CH_CODE[ch] << 6) | ((id >> 8) & 0x3F);
    bb[1] = id & 0xFF;
    bb[2] = (battery ? 0x40 : 0x00) | 0x04;      // message_type = 0x04 (Tower)
    bb[3] = hum & 0x7F;
    int temp_raw = (int)std::lround(temp_c * 10) + 1000;
    bb[4] = (temp_raw >> 7) & 0x7F;
    bb[5] = temp_raw & 0x7F;
    for (int i = 2; i < 6; ++i) bb[i] |= (sentinel::even_parity_bit(bb[i]) << 7);
    int sum = 0;
    for (int i = 0; i < 6; ++i) sum += bb[i];
    bb[6] = sum & 0xFF;

    std::vector<int> bits;
    for (int i = 0; i < 7; ++i)
        for (int k = 7; k >= 0; --k) bits.push_back((bb[i] >> k) & 1);
    return bits;
}

static std::vector<int> nexus_bits(uint32_t id, int channel /*1..3*/, bool battery,
                                   float temp_c, int hum, bool test = false) {
    int temp12 = (int)std::lround(temp_c * 10) & 0xFFF;
    int flags = (battery ? 8 : 0) | (test ? 4 : 0) | (channel - 1);
    int nib[9] = {(int)((id >> 4) & 0xF), (int)(id & 0xF), flags,
                  (temp12 >> 8) & 0xF, (temp12 >> 4) & 0xF, temp12 & 0xF,
                  0xF, (hum >> 4) & 0xF, hum & 0xF};
    std::vector<int> bits;
    for (int n = 0; n < 9; ++n)
        for (int k = 3; k >= 0; --k) bits.push_back((nib[n] >> k) & 1);
    return bits;
}

static std::vector<int> kerui_bits(uint32_t id, int cmd) {
    uint32_t value = (id << 4) | cmd;
    std::vector<int> bits;
    for (int k = 23; k >= 0; --k) bits.push_back((value >> k) & 1);
    return bits;
}

// --------------------------------------------------------------------------
// 用例
// --------------------------------------------------------------------------

static void test_acurite_roundtrip() {
    Frame f;
    CHECK(sentinel::decode_acurite(acurite_bits(12345, 1, true, 21.5f, 55), f));
    CHECK(f.protocol == "acurite");
    CHECK(f.id == 12345);
    CHECK(f.channel == 1);            // 1 = B
    CHECK(f.battery == 1);            // OK
    CHECK_FLOAT(f.temperature_c, 21.5f);
    CHECK(f.humidity == 55);
    CHECK(f.crc_ok == 1);
    CHECK(f.raw_bits.size() == 56);
}

static void test_acurite_crc_pass_fail() {
    Frame f;
    std::vector<int> bits = acurite_bits(9999, 2, true, 0.0f, 40);  // ch=A
    CHECK(sentinel::decode_acurite(bits, f) && f.crc_ok == 1);

    bits[30] ^= 1;                    // 翻转湿度字段中间位
    CHECK(sentinel::decode_acurite(bits, f) && f.crc_ok == 0);
}

static void test_acurite_battery_low_channel_c() {
    Frame f;
    CHECK(sentinel::decode_acurite(acurite_bits(0, 0, false, 25.0f, 1), f));
    CHECK(f.battery == 0);            // LOW
    CHECK(f.channel == 0);            // C
    CHECK(f.crc_ok == 1);
}

static void test_nexus_negative_temp() {
    Frame f;
    CHECK(sentinel::decode_nexus(nexus_bits(0xAB, 2, true, -5.0f, 63), f));
    CHECK(f.protocol == "nexus");
    CHECK(f.id == 0xAB);
    CHECK(f.channel == 2);
    CHECK(f.battery == 1);
    CHECK_FLOAT(f.temperature_c, -5.0f);
    CHECK(f.humidity == 63);
    CHECK(f.crc_ok == 1);
}

static void test_nexus_const_nibble_pass_fail() {
    Frame f;
    std::vector<int> bits = nexus_bits(0x12, 1, true, 20.0f, 50);
    CHECK(sentinel::decode_nexus(bits, f) && f.crc_ok == 1);

    bits[24] ^= 1;                    // 破坏 const nibble（第 6 个 nibble 首 bit）
    CHECK(sentinel::decode_nexus(bits, f) && f.crc_ok == 0);
}

static void test_kerui_roundtrip() {
    Frame f;
    CHECK(sentinel::decode_kerui(kerui_bits(0x3ABCD, 0x2), f));
    CHECK(f.protocol == "kerui");
    CHECK(f.id == 0x3ABCD);
    CHECK(f.cmd == 0x2);
    CHECK(f.crc_ok == -1);            // 无校验位
    CHECK(f.raw_bits.size() == 24);
}

static void test_bit_slicers() {
    std::vector<sentinel::Pulse> pwm = {
        {1, 620.0f}, {0, 596.0f},      // 同步
        {1, 220.0f}, {0, 392.0f},      // 0
        {1, 408.0f}, {0, 204.0f},      // 1
        {1, 220.0f}, {0, 392.0f},      // 0
    };
    auto b = sentinel::pwm_to_bits(pwm, 220.0f, 408.0f, 620.0f, 2192.0f);
    CHECK(b == (std::vector<int>{0, 1, 0}));

    std::vector<sentinel::Pulse> ppm = {
        {1, 500.0f}, {0, 1000.0f},
        {1, 500.0f}, {0, 2000.0f},
        {1, 500.0f}, {0, 1000.0f},
    };
    auto b2 = sentinel::ppm_to_bits(ppm, 500.0f, 1000.0f, 2000.0f, 4000.0f);
    CHECK(b2 == (std::vector<int>{0, 1, 0}));
}

int main() {
    test_acurite_roundtrip();
    test_acurite_crc_pass_fail();
    test_acurite_battery_low_channel_c();
    test_nexus_negative_temp();
    test_nexus_const_nibble_pass_fail();
    test_kerui_roundtrip();
    test_bit_slicers();

    if (g_failures == 0) {
        std::printf("🎉 OOK 解码核心主机测试通过：%d 断言全部通过\n", g_checks);
        return 0;
    }
    std::fprintf(stderr, "❌ %d/%d 断言失败\n", g_failures, g_checks);
    return 1;
}
