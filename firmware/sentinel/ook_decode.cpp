// 边缘频谱哨兵 · OOK 解码核心实现（纯 C++，无 Arduino 依赖）
// 参考 rtl_433（GPL-2.0-or-later）协议文档独立实现，未复制任何 C 代码。
#include "ook_decode.h"

#include <cmath>

namespace sentinel {

namespace {

inline bool close(float w, float ref, float tolerance) {
    return std::fabs(w - ref) <= tolerance * ref;
}

inline int popcount7(int v) {
    int c = 0;
    for (int i = 0; i < 7; ++i) c += (v >> i) & 1;
    return c;
}

inline int signed12(int v) {
    v &= 0xFFF;
    return (v & 0x800) ? (v - 0x1000) : v;
}

}  // namespace

// --------------------------------------------------------------------------
// 位切分
// --------------------------------------------------------------------------

std::vector<int> pwm_to_bits(const std::vector<Pulse>& pulses,
                             float short_us, float long_us,
                             float sync_us, float reset_us, float tolerance) {
    std::vector<int> bits;
    const size_t n = pulses.size();
    size_t i = 0;
    while (i < n) {
        const Pulse& p = pulses[i];
        if (p.level != 1) { ++i; continue; }
        if (sync_us > 0.0f && close(p.width_us, sync_us, tolerance)) {
            i += 2;  // 跳过同步脉冲 + 间隔
            continue;
        }
        int bit;
        if (close(p.width_us, short_us, tolerance)) bit = 0;
        else if (close(p.width_us, long_us, tolerance)) bit = 1;
        else break;  // 未知宽度：噪声/采样异常，停止
        bits.push_back(bit);
        if (i + 1 < n && pulses[i + 1].level == 0) {
            float gap = pulses[i + 1].width_us;
            if (reset_us > 0.0f && gap >= reset_us * (1.0f - tolerance)) break;
        }
        i += 2;
    }
    return bits;
}

std::vector<int> ppm_to_bits(const std::vector<Pulse>& pulses,
                             float pulse_us, float short_gap_us, float long_gap_us,
                             float sync_gap_us, float tolerance) {
    std::vector<int> bits;
    const size_t n = pulses.size();
    size_t i = 0;
    while (i < n) {
        const Pulse& p = pulses[i];
        if (p.level != 1) { ++i; continue; }
        if (!close(p.width_us, pulse_us, tolerance)) { ++i; continue; }
        if (i + 1 < n && pulses[i + 1].level == 0) {
            float gap = pulses[i + 1].width_us;
            if (sync_gap_us > 0.0f && close(gap, sync_gap_us, tolerance)) {
                i += 2;  // 同步间隔，跳过
                continue;
            }
            if (close(gap, short_gap_us, tolerance)) bits.push_back(0);
            else if (close(gap, long_gap_us, tolerance)) bits.push_back(1);
            else break;  // 包尾或噪声
            i += 2;
        } else {
            ++i;
        }
    }
    return bits;
}

// --------------------------------------------------------------------------
// 通用
// --------------------------------------------------------------------------

std::vector<int> invert_bits(const std::vector<int>& bits) {
    std::vector<int> out;
    out.reserve(bits.size());
    for (int b : bits) out.push_back(1 - b);
    return out;
}

std::string bits_to_str(const std::vector<int>& bits) {
    std::string s;
    s.reserve(bits.size());
    for (int b : bits) s.push_back(b ? '1' : '0');
    return s;
}

std::vector<int> bits_to_bytes(const std::vector<int>& bits) {
    std::vector<int> out;
    for (size_t i = 0; i + 8 <= bits.size(); i += 8) {
        int byte = 0;
        for (size_t k = 0; k < 8; ++k) byte = (byte << 1) | bits[i + k];
        out.push_back(byte);
    }
    return out;
}

int even_parity_bit(int low7) { return popcount7(low7 & 0x7F) & 1; }
bool even_parity_ok(int byte) { return even_parity_bit(byte & 0x7F) == ((byte >> 7) & 1); }

// --------------------------------------------------------------------------
// Acurite 592TXR（56bit，解码前整体取反）
// --------------------------------------------------------------------------

bool decode_acurite(const std::vector<int>& bits, Frame& out) {
    if (bits.size() < 56) return false;
    std::vector<int> b = bits_to_bytes(bits);
    if (b.size() < 7) return false;

    int checksum_ok = 0;
    for (int i = 0; i < 6; ++i) checksum_ok += b[i];
    checksum_ok = ((checksum_ok & 0xFF) == b[6]);

    bool parity_ok = true;
    for (int i = 2; i < 6; ++i) parity_ok = parity_ok && even_parity_ok(b[i]);

    int code = (b[0] >> 6) & 0x3;
    // 2bit channel 码 → 规范化数字通道：0=C, 1=B, 2=A, -1=非法(0b01)
    static const int CODE_TO_CHANNEL[4] = {0, -1, 1, 2};
    int channel = CODE_TO_CHANNEL[code];

    out.protocol = "acurite";
    out.id = ((b[0] & 0x3F) << 8) | b[1];
    out.channel = channel;
    out.battery = (b[2] & 0x40) ? 1 : 0;
    out.humidity = b[3] & 0x7F;
    out.has_humidity = true;
    int temp_raw = ((b[4] & 0x7F) << 7) | (b[5] & 0x7F);
    out.temperature_c = (temp_raw - 1000) * 0.1f;
    out.has_temperature = true;
    out.raw_bits = bits_to_str(bits);
    out.crc_ok = (checksum_ok && parity_ok) ? 1 : 0;
    out.cmd = -1;
    return true;
}

// --------------------------------------------------------------------------
// Nexus TH（36bit = 9 nibble，PPM 距离编码）
// --------------------------------------------------------------------------

bool decode_nexus(const std::vector<int>& bits, Frame& out) {
    if (bits.size() < 36) return false;
    int nib[9];
    for (int n = 0; n < 9; ++n) {
        int v = 0;
        for (int k = 0; k < 4; ++k) v = (v << 1) | bits[n * 4 + k];
        nib[n] = v;
    }
    int flags = nib[2];
    int temp12 = (nib[3] << 8) | (nib[4] << 4) | nib[5];

    out.protocol = "nexus";
    out.id = (nib[0] << 4) | nib[1];
    out.channel = (flags & 0x3) + 1;
    out.battery = (flags & 0x8) ? 1 : 0;
    out.temperature_c = signed12(temp12) * 0.1f;
    out.has_temperature = true;
    out.humidity = (nib[7] << 4) | nib[8];
    out.has_humidity = true;
    out.raw_bits = bits_to_str(bits);
    out.crc_ok = (nib[6] == 0xF) ? 1 : 0;
    out.cmd = -1;
    return true;
}

// --------------------------------------------------------------------------
// Kerui / EV1527（24bit = 20bit id + 4bit cmd）
// --------------------------------------------------------------------------

bool decode_kerui(const std::vector<int>& bits, Frame& out) {
    if (bits.size() < 24) return false;
    uint32_t value = 0;
    for (int i = 0; i < 24; ++i) value = (value << 1) | bits[i];

    out.protocol = "kerui";
    out.id = (value >> 4) & 0xFFFFF;   // 高 20bit
    out.cmd = value & 0xF;             // 低 4bit
    out.channel = -1;
    out.battery = -1;
    out.has_temperature = false;
    out.has_humidity = false;
    out.humidity = -1;
    out.raw_bits = bits_to_str(bits);
    out.crc_ok = -1;                   // 无校验位
    return true;
}

// --------------------------------------------------------------------------
// 协议脉冲→bit（时序常量与 Python 侧一致）
// --------------------------------------------------------------------------

namespace {
constexpr float ACURITE_SHORT = 220.0f, ACURITE_LONG = 408.0f;
constexpr float ACURITE_SYNC = 620.0f, ACURITE_RESET = 2192.0f;
constexpr float NEXUS_PULSE = 500.0f, NEXUS_SHORT_GAP = 1000.0f;
constexpr float NEXUS_LONG_GAP = 2000.0f, NEXUS_SYNC_GAP = 4000.0f;
constexpr float KERUI_SHORT = 340.0f, KERUI_LONG = 900.0f;
}  // namespace

std::vector<int> acurite_pulses_to_bits(const std::vector<Pulse>& pulses) {
    return invert_bits(pwm_to_bits(pulses, ACURITE_SHORT, ACURITE_LONG,
                                   ACURITE_SYNC, ACURITE_RESET));
}

std::vector<int> nexus_pulses_to_bits(const std::vector<Pulse>& pulses) {
    return ppm_to_bits(pulses, NEXUS_PULSE, NEXUS_SHORT_GAP, NEXUS_LONG_GAP,
                       NEXUS_SYNC_GAP);
}

std::vector<int> kerui_pulses_to_bits(const std::vector<Pulse>& pulses) {
    std::vector<int> bits;
    const size_t n = pulses.size();
    size_t i = 0;
    while (i < n) {
        const Pulse& p = pulses[i];
        if (p.level != 1) { ++i; continue; }
        // 前置同步位：高脉冲 + 极长间隔 → 跳过（不计 bit）
        if (i + 1 < n && pulses[i + 1].level == 0 && pulses[i + 1].width_us > KERUI_LONG * 2) {
            i += 2;
            continue;
        }
        if (close(p.width_us, KERUI_SHORT, 0.30f)) bits.push_back(0);
        else if (close(p.width_us, KERUI_LONG, 0.30f)) bits.push_back(1);
        else break;
        i += 2;
    }
    return bits;
}

bool decode_any_pulse(const std::vector<Pulse>& pulses, Frame& out) {
    {
        Frame f;
        if (decode_acurite(acurite_pulses_to_bits(pulses), f) && f.crc_ok == 1) {
            out = f;
            return true;
        }
    }
    {
        Frame f;
        if (decode_nexus(nexus_pulses_to_bits(pulses), f) && f.crc_ok == 1) {
            out = f;
            return true;
        }
    }
    {
        Frame f;
        // EV1527 无校验：结构有效即报，重复帧一致性由桥接/上层投票确认
        if (decode_kerui(kerui_pulses_to_bits(pulses), f)) {
            out = f;
            return true;
        }
    }
    return false;
}

}  // namespace sentinel
