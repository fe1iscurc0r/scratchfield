// LoRa 文本帧编解码（卷130 W130-02）——与主机侧 Python 实现逐字节对应
//
// 帧格式（**两侧必须一致**，改动要同步改
// `mcpserver/ptz_service/transport.py` 的 encode_frame/decode_frame/checksum）：
//
//     <payload>#<SUM2>\n
//
//   payload : `PTZ <cmd>`（下行）或 `OK <status>` / `ERR <text>`（上行）
//   SUM2    : payload 的 UTF-8 字节和低 8 位，两位大写十六进制
//   \n      : 帧尾
//
// 校验和选「8 位和」而不是 CRC：工单只要求「长度/校验和」两重校验，
// 而这条链路的错误模型是「无线误码」，不是「恶意篡改」——
// 8 位和足以抓住单比特/短突发错误，且在 8 位 MCU 上几乎零成本。
// （dcp 帧那套 CRC-16 是给二进制载荷用的；这里是文本，用等价的轻量校验更合适。）
//
// 纪律：**校验不过就沉默**。不回 `ERR`——回了会让主机误以为命令被接受了。
#pragma once
#ifndef ANTENNA_LORA_BRIDGE_LORA_LINE_CODEC_HPP_
#define ANTENNA_LORA_BRIDGE_LORA_LINE_CODEC_HPP_

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace antenna {
namespace lora_bridge {

//: 单帧上限（工单 W130-02 §1 规定 ≤64B，含 `#SUM2\n`）
constexpr size_t kFrameMax = 64;
//: 帧前缀
inline const char* kCmdPrefix() { return "PTZ "; }
inline const char* kOkPrefix() { return "OK "; }
inline const char* kErrPrefix() { return "ERR "; }

//: 8 位和无进位校验（与 Python `checksum()` 同式：`sum(payload.encode()) & 0xFF`）
inline uint8_t Checksum(const char* payload, size_t len) {
  uint16_t sum = 0;
  for (size_t i = 0; i < len; ++i) {
    sum = static_cast<uint16_t>(sum + static_cast<uint8_t>(payload[i]));
  }
  return static_cast<uint8_t>(sum & 0xFF);
}

inline uint8_t Checksum(const char* payload) {
  return Checksum(payload, (payload != nullptr) ? strlen(payload) : 0);
}

//: 组帧：`<payload>#<SUM2>\n`。返回写入字节数；超长或参数非法返回 0（**不截断**）。
inline size_t EncodeFrame(const char* payload, uint8_t* out, size_t out_max) {
  if (payload == nullptr || out == nullptr) return 0;
  const size_t len = strlen(payload);
  if (len == 0) return 0;
  // 总长 = payload + '#' + 2 位十六进制 + '\n'
  const size_t total = len + 4;
  if (total > out_max || total > kFrameMax) return 0;
  std::memcpy(out, payload, len);
  out[len] = '#';
  const uint8_t sum = Checksum(payload, len);
  out[len + 1] = static_cast<uint8_t>("0123456789ABCDEF"[(sum >> 4) & 0x0F]);
  out[len + 2] = static_cast<uint8_t>("0123456789ABCDEF"[sum & 0x0F]);
  out[len + 3] = '\n';
  return total;
}

//: 组下行命令帧（主机 → 桥）
inline size_t EncodeCommand(const char* cmd, uint8_t* out, size_t out_max) {
  char buf[kFrameMax] = {0};
  const int n = snprintf(buf, sizeof(buf), "%s%s", kCmdPrefix(),
                         (cmd != nullptr) ? cmd : "");
  if (n <= 0 || static_cast<size_t>(n) >= sizeof(buf)) return 0;
  return EncodeFrame(buf, out, out_max);
}

//: 组上行回复帧（桥 → 主机）。`error:` 开头走 `ERR `，其余走 `OK `。
inline size_t EncodeReply(const char* text, uint8_t* out, size_t out_max) {
  const char* body = (text != nullptr) ? text : "";
  const bool is_err = (strncmp(body, "error:", 6) == 0);
  char buf[kFrameMax] = {0};
  const int n = snprintf(buf, sizeof(buf), "%s%s", is_err ? kErrPrefix() : kOkPrefix(), body);
  if (n <= 0 || static_cast<size_t>(n) >= sizeof(buf)) return 0;
  return EncodeFrame(buf, out, out_max);
}

//: 解帧结果
enum class DecodeStatus : uint8_t {
  kOk = 0,
  kTooShort,      // 不足 `X#HH\n`
  kTooLong,       // 超 kFrameMax
  kNoSeparator,   // 没有 '#'
  kBadChecksum,   // 校验不过（**拒收，且不回 ERR**）
  kBadHex,        // 校验位不是两位十六进制
};

inline const char* DecodeStatusName(DecodeStatus s) {
  switch (s) {
    case DecodeStatus::kOk: return "ok";
    case DecodeStatus::kTooShort: return "too_short";
    case DecodeStatus::kTooLong: return "too_long";
    case DecodeStatus::kNoSeparator: return "no_separator";
    case DecodeStatus::kBadChecksum: return "bad_checksum";
    case DecodeStatus::kBadHex: return "bad_hex";
  }
  return "unknown";
}

//: 解帧：从 `raw`（不含帧尾 \n 也行）解出 payload。
//: `out` 收 payload（不含 `#SUM2`），返回状态。out 长度不足返回 kTooLong。
inline DecodeStatus DecodeFrame(const char* raw, size_t len, char* out, size_t out_max) {
  if (raw == nullptr || out == nullptr || out_max == 0) return DecodeStatus::kTooShort;
  if (len > kFrameMax) return DecodeStatus::kTooLong;
  // 容忍带 \n 的输入（无线收包可能保留帧尾）
  while (len > 0 && (raw[len - 1] == '\n' || raw[len - 1] == '\r')) --len;
  if (len < 4) return DecodeStatus::kTooShort;      // 至少 `X#HH`

  // 从右往左找 '#'：payload 里不应有 '#'，但命令面理论上可能出现，
  // 用 rpartition 语义与 Python 的 `rpartition("#")` 保持一致。
  size_t hash = len;
  for (size_t i = len; i > 0; --i) {
    if (raw[i - 1] == '#') { hash = i - 1; break; }
  }
  if (hash == len) return DecodeStatus::kNoSeparator;
  const size_t payload_len = hash;
  const size_t digest_len = len - hash - 1;
  if (digest_len != 2) return DecodeStatus::kBadHex;

  auto hexval = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
  };
  const int hi = hexval(raw[hash + 1]);
  const int lo = hexval(raw[hash + 2]);
  if (hi < 0 || lo < 0) return DecodeStatus::kBadHex;

  if (payload_len == 0) return DecodeStatus::kTooShort;
  if (payload_len + 1 > out_max) return DecodeStatus::kTooLong;

  const uint8_t expected = static_cast<uint8_t>((hi << 4) | lo);
  if (Checksum(raw, payload_len) != expected) return DecodeStatus::kBadChecksum;

  std::memcpy(out, raw, payload_len);
  out[payload_len] = '\0';
  return DecodeStatus::kOk;
}

//: 去掉 `PTZ ` 前缀 → 纯命令；无前缀返回 nullptr（**不猜**）
inline const char* StripCommandPrefix(const char* payload) {
  if (payload == nullptr) return nullptr;
  const size_t n = strlen(kCmdPrefix());
  if (strncmp(payload, kCmdPrefix(), n) != 0) return nullptr;
  return payload + n;
}

//: 去掉 `OK `/`ERR ` 前缀 → 固件风格回显文本
inline const char* StripReplyPrefix(const char* payload) {
  if (payload == nullptr) return nullptr;
  if (strncmp(payload, kOkPrefix(), strlen(kOkPrefix())) == 0) {
    const char* rest = payload + strlen(kOkPrefix());
    return (rest[0] != '\0') ? rest : "ok";
  }
  if (strncmp(payload, kErrPrefix(), strlen(kErrPrefix())) == 0) {
    return payload + strlen(kErrPrefix());
  }
  return nullptr;
}

}  // namespace lora_bridge
}  // namespace antenna

#endif  // ANTENNA_LORA_BRIDGE_LORA_LINE_CODEC_HPP_
