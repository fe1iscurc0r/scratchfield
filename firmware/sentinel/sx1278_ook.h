// 边缘频谱哨兵 · SX1278 FSK/OOK 模式驱动（Arduino SPI，寄存器级）
//
// 寄存器地址/位域与 Semtech SX1276/77/78 Datasheet 及 RadioLib 常量一致。
// 本阶段只用 OOK 接收（433.92MHz），配置参数与 N-01 勘察报告一致。
#pragma once

#include <Arduino.h>
#include <SPI.h>

namespace sentinel {

// ---- 寄存器地址 ----
enum SxReg : uint8_t {
    REG_OP_MODE       = 0x01,
    REG_FRF_MSB       = 0x06,
    REG_FRF_MID       = 0x07,
    REG_FRF_LSB       = 0x08,
    REG_PA_CONFIG     = 0x09,
    REG_OCP           = 0x0B,
    REG_LNA           = 0x0C,
    REG_RX_CONFIG     = 0x0D,
    REG_RSSI_CONFIG   = 0x0E,
    REG_RSSI_THRESH   = 0x10,
    REG_RSSI_VALUE    = 0x11,   // 只读，实时 RSSI（dBm = -value/2）
    REG_RX_BW         = 0x12,
    REG_OOK_PEAK      = 0x14,
    REG_OOK_FIX       = 0x15,
    REG_IRQ_FLAGS1    = 0x27,
    REG_IRQ_FLAGS2    = 0x28,
    REG_VERSION       = 0x42,
};

// ---- RegOpMode(0x01) 位域 ----
constexpr uint8_t OPMODE_LORA_MASK    = 0x80;
constexpr uint8_t OPMODE_MODULATION_OOK = 0x20;   // bits[6:5]=0b01
constexpr uint8_t OPMODE_MODULATION_FSK = 0x00;   // bits[6:5]=0b00
constexpr uint8_t OPMODE_MODE_SLEEP    = 0x00;
constexpr uint8_t OPMODE_MODE_STDBY    = 0x01;
constexpr uint8_t OPMODE_MODE_RX       = 0x05;

// ---- 频率（433.92MHz）----
// Frf = F_osc / F_step = 433.92e6 / 61.03515625 = 0x6C8000
constexpr uint32_t FRF_433_92 = 0x6C8000UL;

// ---- OOK 接收配置（N-01）----
// RegRxBw(0x12)：Mant=0b10(20)@[4:3]，Exp@[2:0]。Exp=0b100→25kHz；Exp=0b101→12.5kHz
constexpr uint8_t RX_BW_25K    = 0x14;   // 25 kHz（Acurite/Kerui）
constexpr uint8_t RX_BW_12_5K  = 0x15;   // 12.5 kHz（Nexus 慢速可换）
// RegLna(0x0C)：LnaGain=G1(0b001)@[7:5] + LnaBoost=0b11@[1:0]（150% 电流）
constexpr uint8_t LNA_G1_BOOST = 0x23;
// RegOokPeak(0x14)：ThreshType[4:3]=0b00(固定门限)，PeakStep=0b000
constexpr uint8_t OOK_PEAK_FIXED = 0x00;
// RegOokFix(0x15)：OOK 固定门限（按底噪标定，默认 0x08）
constexpr uint8_t OOK_FIX_THRESH = 0x08;
// RegRssiConfig(0x0E)：RssiSmoothing[2:0]=0b000（2 样本，最快边沿响应）
constexpr uint8_t RSSI_SMOOTH_2 = 0x00;
// RegRssiThresh(0x10)：RssiThreshold = 值/2 dBm；0x80 → -64dBm
constexpr uint8_t RSSI_THRESH_64 = 0x80;

class Sx1278Ook {
public:
    Sx1278Ook(int8_t nss, int8_t reset, int8_t dio0 = -1)
        : _nss(nss), _reset(reset), _dio0(dio0) {}

    void begin() {
        pinMode(_nss, OUTPUT);
        digitalWrite(_nss, HIGH);
        pinMode(_reset, OUTPUT);
        digitalWrite(_reset, HIGH);
        if (_dio0 >= 0) pinMode(_dio0, INPUT);

        hardReset();
        uint8_t ver = readRegister(REG_VERSION);
        (void)ver;  // 0x12 = SX1278
    }

    void hardReset() {
        digitalWrite(_reset, LOW);
        delayMicroseconds(100);
        digitalWrite(_reset, HIGH);
        delay(5);
    }

    // 初始化 OOK 接收 @433.92MHz（带宽按 protocol 选择）
    void setOokRx43392(uint8_t rx_bw = RX_BW_25K) {
        // 进入 sleep 后切 FSK/OOK（非 LoRa）
        writeRegister(REG_OP_MODE, OPMODE_MODE_SLEEP | OPMODE_MODULATION_FSK);
        delay(5);
        writeRegister(REG_OP_MODE, OPMODE_MODE_STDBY | OPMODE_MODULATION_OOK);

        // 频率 433.92MHz
        writeRegister(REG_FRF_MSB, (FRF_433_92 >> 16) & 0xFF);
        writeRegister(REG_FRF_MID, (FRF_433_92 >> 8) & 0xFF);
        writeRegister(REG_FRF_LSB, FRF_433_92 & 0xFF);

        // OOK 接收链：带宽 / LNA / 固定门限 / RSSI 平滑
        writeRegister(REG_RX_BW, rx_bw);
        writeRegister(REG_LNA, LNA_G1_BOOST);
        writeRegister(REG_OOK_PEAK, OOK_PEAK_FIXED);
        writeRegister(REG_OOK_FIX, OOK_FIX_THRESH);
        writeRegister(REG_RSSI_CONFIG, RSSI_SMOOTH_2);
        writeRegister(REG_RSSI_THRESH, RSSI_THRESH_64);

        // 进入 RX
        writeRegister(REG_OP_MODE, OPMODE_MODE_RX | OPMODE_MODULATION_OOK);
    }

    void setStandby() {
        writeRegister(REG_OP_MODE, OPMODE_MODE_STDBY | OPMODE_MODULATION_OOK);
    }

    // 实时 RSSI（dBm = -value/2）
    float readRssiDbm() {
        uint8_t v = readRegister(REG_RSSI_VALUE);
        return -static_cast<float>(v) / 2.0f;
    }

    uint8_t readRegister(uint8_t addr) {
        digitalWrite(_nss, LOW);
        SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
        SPI.transfer(addr & 0x7F);      // 读：bit7=0
        uint8_t v = SPI.transfer(0x00);
        SPI.endTransaction();
        digitalWrite(_nss, HIGH);
        return v;
    }

    void writeRegister(uint8_t addr, uint8_t value) {
        digitalWrite(_nss, LOW);
        SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
        SPI.transfer(addr | 0x80);      // 写：bit7=1
        SPI.transfer(value);
        SPI.endTransaction();
        digitalWrite(_nss, HIGH);
    }

    // 供 STATUS 命令回读寄存器快照
    struct Regs {
        uint8_t op_mode, rx_bw, lna, ook_peak, ook_fix, rssi_config, version;
    };
    Regs snapshot() {
        Regs r;
        r.op_mode = readRegister(REG_OP_MODE);
        r.rx_bw = readRegister(REG_RX_BW);
        r.lna = readRegister(REG_LNA);
        r.ook_peak = readRegister(REG_OOK_PEAK);
        r.ook_fix = readRegister(REG_OOK_FIX);
        r.rssi_config = readRegister(REG_RSSI_CONFIG);
        r.version = readRegister(REG_VERSION);
        return r;
    }

private:
    int8_t _nss, _reset, _dio0;
};

}  // namespace sentinel
