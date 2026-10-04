// LoRa 桥主体（卷130 W130-02）——SX1278 收发 + 帧收发记账
//
// 分层：本文件只管「帧进出 + 记账」，`lora_line_codec.hpp` 管编解码，
// `.ino` 管把帧接到串口命令面。三者可各自测试。
//
// 无线电抽成 `Radio` 接口（同卷130 `net/lora_transport.hpp` 的做法）：
//   - 真机：`Sx1278Radio`（RadioLib，编译期按 `ANTENNA_ENABLE_RADIOLIB` 启用）
//   - 自检：`LoopbackRadio`（内存回环，不必插模块就能验证组帧/解帧/应答）
//
// **为什么不直接 include RadioLib**：本机没有 SX1278 硬件，
// 把驱动硬编进来会让「主机端能不能编译/测试」被硬件卡住。
// 用接口隔离后，组帧逻辑是纯 C++（可在任何环境验证），
// 只有 `Sx1278Radio` 那 30 行需要真机。
#pragma once
#ifndef ANTENNA_LORA_BRIDGE_LORA_BRIDGE_HPP_
#define ANTENNA_LORA_BRIDGE_LORA_BRIDGE_HPP_

#include <cstddef>
#include <cstdint>
#include <cstring>

#include "lora_line_codec.hpp"

namespace antenna {
namespace lora_bridge {

//: 无线电参数（工单要求 433MHz 配置化）
struct Config {
  float freq_mhz = 433.0f;
  float bandwidth_khz = 125.0f;
  uint8_t spreading_factor = 7;
  uint8_t coding_rate = 5;
  int8_t power_dbm = 17;
  uint8_t sync_word = 0x12;
};

//: 无线电最小接口
class Radio {
 public:
  virtual ~Radio() = default;
  virtual bool Begin(const Config& cfg) = 0;
  virtual bool Send(const uint8_t* data, size_t len) = 0;
  //: 收一包；无数据返回 0（非阻塞）
  virtual int Receive(uint8_t* out, size_t max_len) = 0;
  virtual bool available() const { return true; }
  virtual int8_t RssiDbm() const { return 0; }
};

//: 回环无线电（自检用：发出去的帧进接收队列）
class LoopbackRadio : public Radio {
 public:
  bool Begin(const Config& cfg) override {
    cfg_ = cfg;
    started_ = true;
    return true;
  }

  bool Send(const uint8_t* data, size_t len) override {
    if (data == nullptr || len == 0 || len > sizeof(rx_)) return false;
    std::memcpy(rx_, data, len);
    rx_len_ = len;
    sent_++;
    return true;
  }

  int Receive(uint8_t* out, size_t max_len) override {
    if (rx_len_ == 0 || out == nullptr || max_len < rx_len_) return 0;
    std::memcpy(out, rx_, rx_len_);
    const int n = static_cast<int>(rx_len_);
    rx_len_ = 0;
    return n;
  }

  const Config& config() const { return cfg_; }
  uint32_t sent_count() const { return sent_; }

 private:
  Config cfg_{};
  uint8_t rx_[kFrameMax] = {0};
  size_t rx_len_ = 0;
  uint32_t sent_ = 0;
  bool started_ = false;
};

//: 桥：帧的收发与记账
class LoraBridge {
 public:
  explicit LoraBridge(Radio* radio = nullptr) : radio_(radio) {}

  void SetRadio(Radio* radio) { radio_ = radio; }

  bool Begin(const Config& cfg) {
    cfg_ = cfg;
    if (radio_ == nullptr) return false;
    return radio_->Begin(cfg);
  }

  // ------------------------------------------------------------------
  // 收
  // ------------------------------------------------------------------

  //: 收一包到缓冲区。返回字节数（0 = 无数据 / -1 = 超长丢弃）
  int RecvFrame() {
    if (radio_ == nullptr) return 0;
    const int got = radio_->Receive(recv_, sizeof(recv_) - 1);
    if (got <= 0) {
      recv_len_ = 0;
      return 0;
    }
    if (static_cast<size_t>(got) > kFrameMax) {
      recv_len_ = 0;
      bad_frames_++;
      return -1;
    }
    recv_len_ = static_cast<size_t>(got);
    recv_[recv_len_] = '\0';
    return got;
  }

  //: 解最近一包。成功时 `last_payload()` 给出去掉 `PTZ ` 前缀的命令。
  bool ParseLastFrame() {
    if (recv_len_ == 0) return false;
    char payload[kFrameMax] = {0};
    const DecodeStatus st = DecodeFrame(recv_, recv_len_, payload, sizeof(payload));
    last_status_ = st;
    if (st != DecodeStatus::kOk) {
      bad_frames_++;               // 校验/格式不过 → 记数并**沉默拒收**
      last_payload_len_ = 0;
      last_payload_[0] = '\0';
      return false;
    }
    const char* cmd = StripCommandPrefix(payload);
    if (cmd == nullptr) {
      // 前缀不对：这不是给命令面的帧（例如遥控端发的状态帧），
      // 也算坏帧但性质不同——分开记，不然排查时分不清是干扰还是误配。
      wrong_prefix_frames_++;
      last_payload_len_ = 0;
      last_payload_[0] = '\0';
      return false;
    }
    const size_t n = strlen(cmd);
    std::memcpy(last_payload_, cmd, n);
    last_payload_[n] = '\0';
    last_payload_len_ = n;
    good_frames_++;
    return true;
  }

  const char* last_payload() const { return last_payload_; }
  size_t last_payload_len() const { return last_payload_len_; }
  DecodeStatus last_status() const { return last_status_; }

  // ------------------------------------------------------------------
  // 发
  // ------------------------------------------------------------------

  //: 回一行状态/回显（`OK <status>` / `ERR <text>`）
  bool SendReply(const char* text) {
    if (radio_ == nullptr) return false;
    uint8_t frame[kFrameMax] = {0};
    const size_t used = EncodeReply(text, frame, sizeof(frame));
    if (used == 0) {
      encode_failures_++;          // 文本太长 → 不截断发送，直接拒
      return false;
    }
    if (!radio_->Send(frame, used)) {
      send_failures_++;
      return false;
    }
    replies_sent_++;
    return true;
  }

  //: 主动推一包自定义文本（例如遥控端心跳）
  bool SendPayload(const char* payload) {
    if (radio_ == nullptr) return false;
    uint8_t frame[kFrameMax] = {0};
    const size_t used = EncodeFrame(payload, frame, sizeof(frame));
    if (used == 0) {
      encode_failures_++;
      return false;
    }
    return radio_->Send(frame, used);
  }

  // ------------------------------------------------------------------
  // 状态上报节拍
  // ------------------------------------------------------------------

  bool StatusDue(uint32_t now_ms) const { return (now_ms - last_status_ms_) >= status_period_ms_; }
  void NoteStatusSent(uint32_t now_ms) { last_status_ms_ = now_ms; }
  void set_status_period_ms(uint32_t ms) { status_period_ms_ = ms; }
  uint32_t status_period_ms() const { return status_period_ms_; }

  //: 主循环钩子（本卷桥无内部时序需求，留接口给后续遥控端复用）
  void Tick(uint32_t now_ms) { (void)now_ms; }

  // ------------------------------------------------------------------
  // 观测
  // ------------------------------------------------------------------

  uint32_t good_frames() const { return good_frames_; }
  uint32_t bad_frames() const { return bad_frames_; }
  uint32_t wrong_prefix_frames() const { return wrong_prefix_frames_; }
  uint32_t replies_sent() const { return replies_sent_; }
  uint32_t send_failures() const { return send_failures_; }
  uint32_t encode_failures() const { return encode_failures_; }
  bool link_up() const { return radio_ != nullptr && radio_->available(); }
  int8_t rssi_dbm() const { return (radio_ != nullptr) ? radio_->RssiDbm() : 0; }
  const Config& config() const { return cfg_; }

 private:
  Radio* radio_ = nullptr;
  Config cfg_{};
  uint8_t recv_[kFrameMax + 1] = {0};
  size_t recv_len_ = 0;
  char last_payload_[kFrameMax] = {0};
  size_t last_payload_len_ = 0;
  DecodeStatus last_status_ = DecodeStatus::kTooShort;
  uint32_t last_status_ms_ = 0;
  uint32_t status_period_ms_ = 1000;

  uint32_t good_frames_ = 0;
  uint32_t bad_frames_ = 0;
  uint32_t wrong_prefix_frames_ = 0;
  uint32_t replies_sent_ = 0;
  uint32_t send_failures_ = 0;
  uint32_t encode_failures_ = 0;
};

}  // namespace lora_bridge
}  // namespace antenna

#endif  // ANTENNA_LORA_BRIDGE_LORA_BRIDGE_HPP_
