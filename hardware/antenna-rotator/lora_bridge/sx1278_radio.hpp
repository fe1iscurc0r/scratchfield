// SX1278 真机驱动（卷130 W130-02）——RadioLib 包装
//
// **编译期按开关启用**：只有定义了 `ANTENNA_ENABLE_RADIOLIB` 才把这个文件编进去。
// 理由：主机端没有 SX1278，也没装 RadioLib；把驱动硬编进来会让
// 「组帧逻辑能不能验证」被硬件卡住。用开关隔离后，
// `lora_line_codec.hpp` / `lora_bridge.hpp`（纯逻辑）在任何环境都能编/测，
// 只有这 30 行需要真板子。
//
// 接线（ESP32-S3 + SX1278 模块，与卷129 参考接线一致）：
//   SX1278  SCK  → GPIO12      SX1278  MISO → GPIO13
//   SX1278  MOSI → GPIO11      SX1278  NSS  → GPIO10
//   SX1278  RST  → GPIO9       SX1278  DIO0 → GPIO8（中断/收包标志，本卷轮询方式）
//   电源 3.3V（**不要接 5V**：SX1278 模块的 IO 不耐 5V）
#pragma once
#ifndef ANTENNA_LORA_BRIDGE_SX1278_RADIO_HPP_
#define ANTENNA_LORA_BRIDGE_SX1278_RADIO_HPP_

#include "lora_bridge.hpp"

#if defined(ANTENNA_ENABLE_RADIOLIB)

#include <RadioLib.h>

namespace antenna {
namespace lora_bridge {

//: ESP32-S3 默认接线（见文件头）
struct Sx1278Pins {
  int sck = 12;
  int miso = 13;
  int mosi = 11;
  int nss = 10;
  int rst = 9;
  int dio0 = 8;
};

class Sx1278Radio : public Radio {
 public:
  explicit Sx1278Radio(const Sx1278Pins& pins = Sx1278Pins())
      : module_(new Module(pins.nss, pins.dio0, pins.rst, RADIOLIB_NC)),
        radio_(new SX1278(module_)) {}

  ~Sx1278Radio() override {
    delete radio_;
    delete module_;
  }

  bool Begin(const Config& cfg) override {
    // 1) LoRa 调制参数
    const int16_t st = radio_->begin(cfg.freq_mhz, cfg.bandwidth_khz,
                                     cfg.spreading_factor, cfg.coding_rate,
                                     cfg.sync_word, cfg.power_dbm);
    if (st != RADIOLIB_ERR_NONE) return false;
    // 2) 收包超时给 0 → 非阻塞语义，与 Radio 接口约定一致
    radio_->setPacketReceivedAction(nullptr);
    radio_->startReceive();
    ready_ = true;
    return true;
  }

  bool Send(const uint8_t* data, size_t len) override {
    if (!ready_ || data == nullptr || len == 0) return false;
    // 发之前必须先停接收，否则 SX1278 处于 RX 状态时无法切到 TX
    radio_->standby();
    const int16_t st = radio_->transmit(data, len);
    radio_->startReceive();           // 立刻回到收模式（桥要随时能收命令）
    return st == RADIOLIB_ERR_NONE;
  }

  int Receive(uint8_t* out, size_t max_len) override {
    if (!ready_ || out == nullptr) return 0;
    const size_t len = radio_->getPacketLength();
    if (len == 0 || len > max_len) return 0;
    const int16_t st = radio_->readData(out, len);
    radio_->startReceive();           // 收完立刻续上，避免漏下一包
    if (st != RADIOLIB_ERR_NONE) return 0;
    return static_cast<int>(len);
  }

  bool available() const override { return ready_; }
  int8_t RssiDbm() const override {
    return ready_ ? static_cast<int8_t>(radio_->getRSSI()) : 0;
  }

 private:
  Module* module_ = nullptr;
  SX1278* radio_ = nullptr;
  bool ready_ = false;
};

}  // namespace lora_bridge
}  // namespace antenna

#endif  // ANTENNA_ENABLE_RADIOLIB

#endif  // ANTENNA_LORA_BRIDGE_SX1278_RADIO_HPP_
