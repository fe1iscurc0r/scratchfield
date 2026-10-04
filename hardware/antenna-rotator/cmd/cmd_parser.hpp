// 轨迹插补命令面（卷129 W129-04）——GRBL 式 G 代码子集 + 直线插补 + 串口 REPL
//
// 授粉参考（机制，不整抄）：GRBL 的命令解释器与直线插补语义（两轴耗时相等，慢轴全速、
// 快轴按比例降速）。本文件实现子集：G0/G1（快速/直线定位）、G28（回零）、G4（暂停）、
// M114（状态查询）、M17/M18（使能/释放）；未知命令返回 `error:unknown`。
//
// 分层：解析与插补是**纯 C++**（主机端可测），串口读写抽象成 `ReplTransport`
// （真机绑 Serial，自检用内存队列）。

#pragma once

#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace antenna {

enum class GcodeId : uint8_t {
  kNone = 0,
  kG0,   // 快速定位（按各轴最大速度，不保证同时到达）
  kG1,   // 直线插补（两轴同时到达）
  kG4,   // 暂停（P 秒）
  kG28,  // 回零
  kM17,  // 使能
  kM18,  // 释放
  kM114, // 状态查询
};

struct GcodeCommand {
  GcodeId id = GcodeId::kNone;
  bool ok = false;
  float x = NAN;         // 方位角（度）
  float y = NAN;         // 俯仰角（度）
  float f = NAN;         // 进给速度（度/秒）
  float p = NAN;         // 暂停时长（秒）
  char error[32] = {0};  // 解析失败原因
};

//: 极简解析：`G0 X30 Y-10 F5` / `M114` / `G4 P1.5`（大小写不敏感，忽略多余空格）
inline GcodeCommand ParseGcode(const char* line) {
  GcodeCommand cmd;
  if (line == nullptr) {
    snprintf(cmd.error, sizeof(cmd.error), "empty");
    return cmd;
  }
  char buffer[128];
  size_t n = 0;
  for (const char* p = line; *p != '\0' && n < sizeof(buffer) - 1; p++) {
    buffer[n++] = static_cast<char>(toupper(*p));
  }
  buffer[n] = '\0';

  char* token = strtok(buffer, " \t\r\n");
  bool have_g = false;
  bool have_m = false;
  while (token != nullptr) {
    if (token[0] == ';') break;  // 注释到行尾
    if (token[0] == 'G' || token[0] == 'M') {
      const int code = atoi(token + 1);
      if (token[0] == 'G') {
        switch (code) {
          case 0: cmd.id = GcodeId::kG0; have_g = true; break;
          case 1: cmd.id = GcodeId::kG1; have_g = true; break;
          case 4: cmd.id = GcodeId::kG4; have_g = true; break;
          case 28: cmd.id = GcodeId::kG28; have_g = true; break;
          default:
            snprintf(cmd.error, sizeof(cmd.error), "unsupported_g%d", code);
            return cmd;
        }
      } else {
        switch (code) {
          case 17: cmd.id = GcodeId::kM17; have_m = true; break;
          case 18: cmd.id = GcodeId::kM18; have_m = true; break;
          case 114: cmd.id = GcodeId::kM114; have_m = true; break;
          default:
            snprintf(cmd.error, sizeof(cmd.error), "unsupported_m%d", code);
            return cmd;
        }
      }
    } else if (token[0] == 'X') {
      cmd.x = strtof(token + 1, nullptr);
    } else if (token[0] == 'Y') {
      cmd.y = strtof(token + 1, nullptr);
    } else if (token[0] == 'F') {
      cmd.f = strtof(token + 1, nullptr);
    } else if (token[0] == 'P') {
      cmd.p = strtof(token + 1, nullptr);
    }
    token = strtok(nullptr, " \t\r\n");
  }
  if (!have_g && !have_m) {
    snprintf(cmd.error, sizeof(cmd.error), "unknown");
    return cmd;
  }
  cmd.ok = true;
  return cmd;
}

//: 直线插补速度分配：两轴耗时相等 → 慢轴（角度行程短）按比例降速
//:   返回各轴速度（度/秒）；总时长 = max(|dx|,|dy|) / f
struct InterpPlan {
  float v_az_deg_s = 0.0f;
  float v_el_deg_s = 0.0f;
  float duration_s = 0.0f;
  bool ok = false;
};

inline InterpPlan PlanLinear(float dx_deg, float dy_deg, float feed_deg_s) {
  InterpPlan plan;
  const float dx = fabsf(dx_deg), dy = fabsf(dy_deg);
  const float longest = fmaxf(dx, dy);
  if (!isfinite(dx_deg) || !isfinite(dy_deg) || feed_deg_s <= 0.0f || longest <= 1e-6f) {
    return plan;  // 无位移或速度非法：调用方按「已在目标」处理
  }
  plan.duration_s = longest / feed_deg_s;
  plan.v_az_deg_s = fabsf(dx_deg) / plan.duration_s;
  plan.v_el_deg_s = fabsf(dy_deg) / plan.duration_s;
  plan.ok = true;
  return plan;
}

//: 串口/链路传输抽象：真机绑 Serial，自检用内存缓冲
class ReplTransport {
 public:
  virtual ~ReplTransport() = default;
  //: 取一行（无数据返回 false）
  virtual bool ReadLine(char* out, size_t max_len) = 0;
  //: 写一行（实现负责补换行）
  virtual void WriteLine(const char* text) = 0;
};

//: 状态回调：命令面不直接碰硬件，通过这个接口驱动运动层（由上层实现）
class MotionCommandSink {
 public:
  virtual ~MotionCommandSink() = default;
  //: G0/G1：移动到目标（返回错误字符串，nullptr = 接受）
  virtual const char* MoveTo(float az_deg, float el_deg, float feed_deg_s, bool linear) = 0;
  virtual const char* Home() = 0;
  virtual void Hold(float seconds) = 0;
  virtual void Enable(bool on) = 0;
  virtual const char* StatusLine(char* out, size_t max_len) = 0;
};

//: 命令解释器：解析 → 驱动 sink → 回显 `ok` / `error:...`
class CommandInterpreter {
 public:
  explicit CommandInterpreter(MotionCommandSink* sink) : sink_(sink) {}

  //: 处理一行命令，把回显写回 transport；返回 false 表示链路应停止
  bool HandleLine(const char* line, ReplTransport* transport) {
    if (transport == nullptr) return false;
    const GcodeCommand cmd = ParseGcode(line);
    if (!cmd.ok) {
      char out[64];
      snprintf(out, sizeof(out), "error:%s", cmd.error[0] ? cmd.error : "unknown");
      transport->WriteLine(out);
      return true;
    }
    if (sink_ == nullptr) {
      transport->WriteLine("error:no_sink");
      return true;
    }
    switch (cmd.id) {
      case GcodeId::kG0:
      case GcodeId::kG1: {
        const float feed = isfinite(cmd.f) ? cmd.f : 10.0f;  // 默认 10°/s
        const char* err = sink_->MoveTo(cmd.x, cmd.y, feed, cmd.id == GcodeId::kG1);
        transport->WriteLine(err == nullptr ? "ok" : err);
        break;
      }
      case GcodeId::kG28: {
        const char* err = sink_->Home();
        transport->WriteLine(err == nullptr ? "ok" : err);
        break;
      }
      case GcodeId::kG4:
        sink_->Hold(isfinite(cmd.p) ? cmd.p : 0.0f);
        transport->WriteLine("ok");
        break;
      case GcodeId::kM17:
        sink_->Enable(true);
        transport->WriteLine("ok");
        break;
      case GcodeId::kM18:
        sink_->Enable(false);
        transport->WriteLine("ok");
        break;
      case GcodeId::kM114: {
        char status[160];
        const char* err = sink_->StatusLine(status, sizeof(status));
        transport->WriteLine(err == nullptr ? status : err);
        break;
      }
      default:
        transport->WriteLine("error:unknown");
        break;
    }
    return true;
  }

  //: 跑一轮（处理所有待读行）；返回处理的行数
  uint32_t Poll(ReplTransport* transport) {
    uint32_t handled = 0;
    char line[128];
    while (transport != nullptr && transport->ReadLine(line, sizeof(line))) {
      HandleLine(line, transport);
      handled++;
    }
    return handled;
  }

 private:
  MotionCommandSink* sink_ = nullptr;
};

}  // namespace antenna
