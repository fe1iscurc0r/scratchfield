// 边缘频谱哨兵 · OOK 解码核心（纯 C++，无 Arduino 依赖，可主机编译）
//
// 参考 rtl_433（GPL-2.0-or-later）协议文档，仅引用「协议格式」公开事实，
// 独立实现，未复制任何 C 代码。与 mcpserver/rf_brain/decoders/ook/ 的 Python
// 实现（N-02）逐位对齐——本文件是同一算法的 C++ 端口，供 ESP32-S3 固件复用。
//
// 帧格式与 Python 侧完全一致：
//   Acurite 592TXR  OOK-PWM  56bit  加和校验 + 偶校验
//   Nexus TH        OOK-PPM  36bit  固定 0xF nibble（有符号 12bit 温度）
//   Kerui/EV1527    OOK-PWM  24bit  20bit id + 4bit cmd（无校验）
#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace sentinel {

struct Pulse {
    int level = 0;      // 1=高电平（载波在），0=低电平
    float width_us = 0.0f;
};

struct Frame {
    std::string protocol;
    uint32_t id = 0;
    int channel = -1;           // acurite: 0=C 1=B 2=A（-1 非法）；nexus: 1..3；kerui: -1
    bool has_temperature = false;
    float temperature_c = 0.0f;
    bool has_humidity = false;
    int humidity = -1;
    int battery = -1;           // 1=OK 0=LOW -1=unknown
    std::string raw_bits;
    int crc_ok = -1;            // 1=通过 0=失败 -1=无校验
    int cmd = -1;               // kerui 命令码
};

// ---- 位切分（与 pulse_demod.py 同源） ----
std::vector<int> pwm_to_bits(const std::vector<Pulse>& pulses,
                             float short_us, float long_us,
                             float sync_us, float reset_us,
                             float tolerance = 0.30f);
std::vector<int> ppm_to_bits(const std::vector<Pulse>& pulses,
                             float pulse_us, float short_gap_us, float long_gap_us,
                             float sync_gap_us, float tolerance = 0.30f);

// ---- 通用 ----
std::vector<int> invert_bits(const std::vector<int>& bits);
std::string bits_to_str(const std::vector<int>& bits);
std::vector<int> bits_to_bytes(const std::vector<int>& bits);
int even_parity_bit(int low7);
bool even_parity_ok(int byte);

// ---- 协议解码（返回 false = 结构错误/bit 不足；true = 已产出 Frame，含 crc_ok） ----
bool decode_acurite(const std::vector<int>& bits, Frame& out);
bool decode_nexus(const std::vector<int>& bits, Frame& out);
bool decode_kerui(const std::vector<int>& bits, Frame& out);

// ---- 协议脉冲→bit（含各自时序常量）----
std::vector<int> acurite_pulses_to_bits(const std::vector<Pulse>& pulses);
std::vector<int> nexus_pulses_to_bits(const std::vector<Pulse>& pulses);
std::vector<int> kerui_pulses_to_bits(const std::vector<Pulse>& pulses);

// ---- 脉冲→任一协议帧（固件接收循环入口）----
bool decode_any_pulse(const std::vector<Pulse>& pulses, Frame& out);

}  // namespace sentinel
