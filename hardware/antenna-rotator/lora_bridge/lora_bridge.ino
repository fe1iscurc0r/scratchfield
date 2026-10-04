// LoRa433 遥控桥（卷130 W130-02）——串口命令面 ↔ SX1278 无线，两条控制路并存
//
// 工单 W130-02 §1 规定的帧（**文本**，与主机侧 `mcpserver/ptz_service/transport.py`
// 的 `encode_frame`/`decode_frame` 逐字节对应）：
//
//     下行 主机 → 桥   `PTZ <cmd>#<SUM2>\n`      （≤64B）
//     上行 桥 → 主机   `OK <status>#<SUM2>\n`  或  `ERR <text>#<SUM2>\n`
//
// `<SUM2>` 是 payload（含 `PTZ `/`OK ` 前缀、不含 `#`）的 8 位和无进位校验的两位十六进制。
// **为什么用文本而不是 dcp 二进制帧**：工单 W130-02 明写文本帧；
// 且卷129 的命令面本身就是 ASCII 行协议（`ok`/`error:limit`），
// 无线侧再包一层二进制反而要在桥里做「二进制↔文本」的有损翻译——
// 而回显文本是跨层协议，多一次翻译就多一处可能不一致的事实源。
//
// 桥的职责刻意做小：**只做帧的收发与校验，不做语义解释**。
// 收到 `PTZ G1 X30` 就把 `G1 X30` 原样喂给串口命令面，拿到什么回显就原样回传。
// 这样命令面的新增指令（M112/$X/! 等）不需要改桥。
//
// 依赖：RadioLib（SX1278 驱动）。平台配置见 platformio.ini。

#include <Arduino.h>

#include "lora_bridge.hpp"
#include "lora_line_codec.hpp"

namespace {

// ---------------- 配置（改这里而不改逻辑） ----------------

//: 串口波特率须与卷129 命令面一致
constexpr uint32_t kSerialBaud = 115200;
//: LoRa 频点（433MHz 段，配置化；各国法规不同，部署前按当地 ISM 规则确认）
constexpr float kLoraFreqMhz = 433.0f;
//: 扩频参数：空口速率与灵敏度的权衡。125kHz/7 是速度优先，适合遥控
constexpr float kLoraBandwidthKhz = 125.0f;
constexpr uint8_t kLoraSf = 7;
constexpr uint8_t kLoraCr = 5;          // 4/5
constexpr int8_t kLoraPowerDbm = 17;    // SX1278 高功率档
//: 同步字——与遥控端约定；避免和本仓其他 433 设备串台
constexpr uint8_t kLoraSyncWord = 0x12;
//: 单包上限（工单规定 ≤64B）
constexpr size_t kFrameMax = antenna::lora_bridge::kFrameMax;

//: 状态上报节拍（工单 W130-02 §1「状态回传无线」）
constexpr uint32_t kStatusPeriodMs = 1000;
//: 串口回显等待上限——命令面是同步的，超时即视为设备异常
constexpr uint32_t kSerialReplyTimeoutMs = 800;

antenna::lora_bridge::LoraBridge bridge;

}  // namespace

// ---------------------------------------------------------------------------
// 回流（把桥收到的帧交给串口命令面，取回显再回发无线）
// ---------------------------------------------------------------------------

//: 桥的解帧结果 → 串口命令面。返回 false 表示该帧无效（已记 bad_frames）。
static bool ForwardToCommandFace(const char* payload, size_t len, char* reply, size_t reply_max) {
  if (payload == nullptr || reply == nullptr || reply_max == 0) return false;
  // 1) 转发命令（原样，不做任何改写——命令面才是唯一解释者）
  Serial.write(reinterpret_cast<const uint8_t*>(payload), len);
  Serial.write('\n');

  // 2) 等一行回显（`ok` / `error:xxx` / 状态行）
  const uint32_t deadline = millis() + kSerialReplyTimeoutMs;
  size_t used = 0;
  bool got_line = false;
  while (millis() < deadline) {
    while (Serial.available() > 0) {
      const int ch = Serial.read();
      if (ch < 0) break;
      if (ch == '\n' || ch == '\r') {
        got_line = used > 0;
        if (got_line) break;
        continue;                       // 忽略空行（固件可能连发 CRLF）
      }
      if (used + 1 < reply_max) reply[used++] = static_cast<char>(ch);
    }
    if (got_line) break;
    delay(1);
  }
  reply[used] = '\0';
  if (!got_line) {
    snprintf(reply, reply_max, "error:timeout");
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------
// Arduino 生命周期
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(kSerialBaud);

  antenna::lora_bridge::Config cfg;
  cfg.freq_mhz = kLoraFreqMhz;
  cfg.bandwidth_khz = kLoraBandwidthKhz;
  cfg.spreading_factor = kLoraSf;
  cfg.coding_rate = kLoraCr;
  cfg.power_dbm = kLoraPowerDbm;
  cfg.sync_word = kLoraSyncWord;

  if (!bridge.Begin(cfg)) {
    // 无线电起不来：桥不能假装在工作。串口上留一条明确日志，
    // 主机侧会看到 PTZ 命令永远无回显 → 走 W130-04 的心跳兜底。
    Serial.println("error:lora_init");
    return;
  }
  Serial.println("ok:lora_bridge_ready");
}

void loop() {
  bridge.Tick(millis());

  // 收包 → 解帧 → 转串口 → 回传
  const int got = bridge.RecvFrame();
  if (got > 0) {
    if (bridge.ParseLastFrame()) {
      char reply[kFrameMax] = {0};
      ForwardToCommandFace(bridge.last_payload(), bridge.last_payload_len(),
                           reply, sizeof(reply));
      bridge.SendReply(reply);
    }
    // 校验失败：`ParseLastFrame` 已记 bad_frames 并拒收，**不回任何东西**
    // ——回了会让主机以为这条命令被接受了（沉默才是正确的"我没听懂"）。
  }

  // 周期性状态上报：主机靠它判断桥还活着（W130-04 心跳的无线侧对端）
  if (bridge.StatusDue(millis())) {
    char status[kFrameMax] = {0};
    if (ForwardToCommandFace("M114", 4, status, sizeof(status))) {
      bridge.SendReply(status);
    }
    bridge.NoteStatusSent(millis());
  }
}
