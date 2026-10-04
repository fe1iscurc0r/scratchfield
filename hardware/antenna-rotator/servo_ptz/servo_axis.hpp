// 舵机云台 PTZ 服务（卷129 W129-03）——平滑渐变 + 限位保护 + 多轴群控
//
// 设计取舍：**不直接依赖外部 Servo 库**，而是把「往硬件写脉宽」抽成 `ServoOutput` 接口——
// 真机实现（LEDC / ESP32Servo）由上层注入，自检与主机端可用记录型实现。
// 好处：①编译不被第三方库版本左右 ②平滑算法与状态机可在无硬件时被验证
//      ③B 方案云台是「方位步进 + 俯仰舵机」混合轴，抽象后两种输出可并存。
//
// 授粉参考（机制）：ServoEasing 的步进式渐变思路——每 20ms 走 2~3°，避免舵机突跳。

#pragma once

#include <cmath>
#include <cstdint>
#include <cstring>

namespace antenna {

//: 舵机脉宽范围（MG90S 类常见 500~2500us 对应 0~180°）
struct ServoCalibration {
  uint16_t min_us = 500;
  uint16_t max_us = 2500;
  float min_deg = 0.0f;
  float max_deg = 180.0f;

  uint16_t DegToUs(float deg) const {
    float clamped = deg;
    if (clamped < min_deg) clamped = min_deg;
    if (clamped > max_deg) clamped = max_deg;
    const float ratio = (max_deg > min_deg) ? (clamped - min_deg) / (max_deg - min_deg) : 0.0f;
    return static_cast<uint16_t>(min_us + ratio * (max_us - min_us));
  }
};

//: 硬件输出抽象：真机 = LEDC/ESP32Servo；自检 = 记录器
class ServoOutput {
 public:
  virtual ~ServoOutput() = default;
  virtual void WriteUs(uint16_t pulse_us) = 0;
  virtual uint16_t LastUs() const = 0;
  virtual const char* Name() const { return "servo-output"; }
};

//: 记录型输出（自检/主机端用）：保存最后一次脉宽与写入次数
class RecordingServoOutput : public ServoOutput {
 public:
  void WriteUs(uint16_t pulse_us) override {
    last_us_ = pulse_us;
    writes_++;
  }
  uint16_t LastUs() const override { return last_us_; }
  const char* Name() const override { return "recording"; }
  uint32_t writes() const { return writes_; }

 private:
  uint16_t last_us_ = 0;
  uint32_t writes_ = 0;
};

//: 轴状态（供卷130 MCP 服务读取）
struct AxisStatus {
  uint8_t id = 0;
  float target_deg = 0.0f;
  float current_deg = 0.0f;
  bool moving = false;
  bool fault = false;
  const char* fault_reason = "";
};

//: 单轴舵机：平滑渐变 + 软限位 + 堵转保护
class ServoAxis {
 public:
  struct Config {
    float step_deg = 2.5f;         // 每个节拍最大转角（防突跳）
    uint32_t tick_ms = 20;         // 节拍（20ms ≈ 50Hz 舵机刷新）
    float tolerance_deg = 0.5f;    // 到位判定
    float stall_current_a = 0.0f;  // 堵转电流阈值（0 = 不启用）
    bool invert = false;           // 机械反向安装
  };

  ServoAxis(uint8_t id, ServoOutput* output, const ServoCalibration& cal)
      : id_(id), output_(output), cal_(cal) {}
  ServoAxis(uint8_t id, ServoOutput* output, const ServoCalibration& cal, const Config& cfg)
      : id_(id), output_(output), cal_(cal), cfg_(cfg) {}

  void Attach(float current_deg) {
    current_deg_ = Clamp(current_deg);
    target_deg_ = current_deg_;
    if (output_ != nullptr) output_->WriteUs(cal_.DegToUs(OutputDeg(current_deg_)));
  }

  //: 设定目标（越限/非法 → 拒绝，不动，并给出原因字符串）
  //:   **不清除 stall 故障**：堵转属于硬件异常，必须显式 ClearFault() 确认后才恢复，
  //:   否则「设个新目标就继续跑」会在机械卡死时反复冲击舵机（规格测试抓到过）
  bool SetTarget(float deg, const char** out_reason = nullptr) {
    if (!isfinite(deg)) return Reject("invalid", out_reason);
    if (deg < cal_.min_deg || deg > cal_.max_deg) return Reject("limit", out_reason);
    if (fault_ && fault_reason_ != nullptr && strcmp(fault_reason_, "stall") == 0) {
      if (out_reason != nullptr) *out_reason = "stall";
      return false;
    }
    target_deg_ = deg;
    fault_ = false;
    fault_reason_ = "";
    return true;
  }

  //: 推进一个节拍（由上层定时调用，或 Step(dt) 内部按 tick 计时）
  bool Tick() {
    if (fault_) return false;
    const float diff = target_deg_ - current_deg_;
    if (fabsf(diff) <= cfg_.tolerance_deg) {
      current_deg_ = target_deg_;  // 咬合到目标，避免残差
      if (output_ != nullptr) output_->WriteUs(cal_.DegToUs(OutputDeg(current_deg_)));
      return false;
    }
    const float step = (diff > 0 ? 1.0f : -1.0f) * fminf(cfg_.step_deg, fabsf(diff));
    current_deg_ += step;
    if (output_ != nullptr) output_->WriteUs(cal_.DegToUs(OutputDeg(current_deg_)));
    return true;
  }

  //: 注入电流采样（ADC，单位 A）；超阈值 → fault（三保险第二环）
  bool SampleCurrent(float amps) {
    if (cfg_.stall_current_a > 0.0f && amps > cfg_.stall_current_a) {
      fault_ = true;
      fault_reason_ = "stall";
      return false;
    }
    return true;
  }

  void ClearFault() {
    fault_ = false;
    fault_reason_ = "";
  }

  AxisStatus Status() const {
    AxisStatus st;
    st.id = id_;
    st.target_deg = target_deg_;
    st.current_deg = current_deg_;
    st.moving = fabsf(target_deg_ - current_deg_) > cfg_.tolerance_deg;
    st.fault = fault_;
    st.fault_reason = fault_reason_;
    return st;
  }

  float current_deg() const { return current_deg_; }
  float target_deg() const { return target_deg_; }
  bool moving() const { return Status().moving; }
  bool fault() const { return fault_; }
  const ServoCalibration& calibration() const { return cal_; }

 private:
  float Clamp(float deg) const {
    if (deg < cal_.min_deg) return cal_.min_deg;
    if (deg > cal_.max_deg) return cal_.max_deg;
    return deg;
  }
  float OutputDeg(float deg) const { return cfg_.invert ? (cal_.min_deg + cal_.max_deg - deg) : deg; }
  bool Reject(const char* reason, const char** out_reason) {
    fault_ = true;
    fault_reason_ = reason;
    if (out_reason != nullptr) *out_reason = reason;
    return false;
  }

  uint8_t id_ = 0;
  ServoOutput* output_ = nullptr;
  ServoCalibration cal_{};
  Config cfg_{};
  float current_deg_ = 0.0f;
  float target_deg_ = 0.0f;
  bool fault_ = false;
  const char* fault_reason_ = "";
};

//: 多轴群控：并行渐变（每轴按自己节拍走到目标），支持混合轴（步进 + 舵机）
class PtzManager {
 public:
  static constexpr uint8_t kMaxAxes = 4;

  bool Add(ServoAxis* axis) {
    if (axis == nullptr || count_ >= kMaxAxes) return false;
    axes_[count_++] = axis;
    return true;
  }

  uint8_t count() const { return count_; }

  //: 并行移动到目标（全部拒绝则返回 false；部分成功返回 true 并在状态里体现 fault）
  bool MoveAll(const float* targets, uint8_t n) {
    if (targets == nullptr || n > count_) return false;
    bool any_ok = false;
    for (uint8_t i = 0; i < n; i++) {
      if (axes_[i]->SetTarget(targets[i])) any_ok = true;
    }
    return any_ok;
  }

  //: 推进所有轴一个节拍；返回仍在运动的轴数
  uint8_t TickAll() {
    uint8_t moving = 0;
    for (uint8_t i = 0; i < count_; i++) {
      if (axes_[i]->Tick()) moving++;
    }
    return moving;
  }

  //: 并行推进到全部到位或超时，返回是否全部到位
  bool RunToTargets(uint32_t timeout_ms, uint32_t tick_ms = 20) {
    uint32_t waited = 0;
    while (waited <= timeout_ms) {
      const uint8_t moving = TickAll();
      if (moving == 0) return true;
      waited += tick_ms;
    }
    return false;
  }

  AxisStatus Status(uint8_t index) const {
    if (index >= count_) return AxisStatus{};
    return axes_[index]->Status();
  }

 private:
  ServoAxis* axes_[kMaxAxes] = {nullptr};
  uint8_t count_ = 0;
};

}  // namespace antenna
