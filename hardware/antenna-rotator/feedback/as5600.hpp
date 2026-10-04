// AS5600 磁编码器闭环（卷129 W129-02）——云台「三保险」第一环
//
// 职责：绝对角度回读（I2C 0x36，12bit 0..4095）→ 角度换算 → 抖动滤波 → 零点偏移 →
//       闭环归零（写入 NVS 断电记忆）→ 自校准（往返扫描，检测非线性/丢步）。
//
// 设计要点
// --------
// - **角度源可注入**：`AngleSource` 抽象接口，真机上用 `As5600Source`（I2C），
//   自检/无硬件时用 `SyntheticSource`（正弦/斜坡）——这样闭环与校准逻辑能在无硬件时也被验证。
// - **不吞错**：I2C 读失败返回 `ok=false`，由调用方决定降级（连续失败 → fault）。
// - 参考 TMC 闭环语义（位置误差 → 微调），但我们用编码器回读，**不依赖驱动芯片**。

#pragma once

#include <cmath>
#include <cstdint>
#include <cstdio>

namespace antenna {

//: 12bit 编码器原始值 → 度数
constexpr float kAs5600Counts = 4096.0f;
inline float CountsToDeg(uint16_t counts) {
  return (static_cast<float>(counts & 0x0FFFu) / kAs5600Counts) * 360.0f;
}
inline uint16_t DegToCounts(float deg) {
  float v = fmodf(deg, 360.0f);
  if (v < 0.0f) v += 360.0f;
  return static_cast<uint16_t>((v / 360.0f) * kAs5600Counts) & 0x0FFF;
}

//: 角度源抽象：真机 = I2C 芯片，测试 = 合成信号
class AngleSource {
 public:
  virtual ~AngleSource() = default;
  //: 读一次原始角度（度，0..360）；失败返回 false（角度值无效）
  virtual bool ReadDeg(float* out_deg) = 0;
  virtual const char* Name() const = 0;
};

//: 合成源（无硬件自检用）：按时间做正弦/斜坡/跳变，可注入丢步与非线性
class SyntheticSource : public AngleSource {
 public:
  explicit SyntheticSource(float period_s = 4.0f) : period_s_(period_s) {}

  bool ReadDeg(float* out_deg) override {
    if (out_deg == nullptr) return false;
    const float deg = 180.0f + 170.0f * sinf(2.0f * PI_ * t_ / period_s_);
    *out_deg = Nonlinearity(deg) + injected_step_deg_;
    t_ += dt_;
    if (fail_after_ > 0 && --fail_after_ == 0) return false;  // 模拟 I2C 失败
    return true;
  }
  const char* Name() const override { return "synthetic"; }

  void set_dt(float dt_s) { dt_ = dt_s; }
  void inject_step(float deg) { injected_step_deg_ = deg; }
  void fail_next(int n) { fail_after_ = n; }

 private:
  //: 非线性：给正弦加一点二次畸变，供自校准检测
  float Nonlinearity(float deg) const {
    const float norm = (deg - 180.0f) / 180.0f;  // -1..1
    return deg + 1.5f * norm * norm * (norm > 0 ? 1.0f : -1.0f);
  }

  static constexpr float PI_ = 3.14159265358979f;
  float period_s_;
  float t_ = 0.0f;
  float dt_ = 0.01f;
  float injected_step_deg_ = 0.0f;
  int fail_after_ = 0;
};

//: 抖动滤波 + 零点偏移的编码器读数封装
class As5600Reader {
 public:
  struct Config {
    float zero_offset_deg = 0.0f;   // 零点偏移（归零写入 NVS 后回填）
    uint8_t filter_window = 3;      // 滑动平均窗口（1 = 不滤波）
    float jitter_warn_deg = 5.0f;   // 单次跳变超此值记为可疑（丢步/干扰）
  };

  explicit As5600Reader(AngleSource* source) : source_(source) {}
  As5600Reader(AngleSource* source, const Config& cfg) : source_(source), cfg_(cfg) {}

  const Config& config() const { return cfg_; }
  void set_zero_offset(float deg) { cfg_.zero_offset_deg = deg; }
  float zero_offset_deg() const { return cfg_.zero_offset_deg; }
  uint32_t read_failures() const { return read_failures_; }
  uint32_t jitter_events() const { return jitter_events_; }

  //: 读一次**已滤波 + 已去零点**的角度；失败返回 false（调用方可据此降级/告警）
  bool ReadDeg(float* out_deg) {
    if (source_ == nullptr || out_deg == nullptr) return false;
    float raw = 0.0f;
    if (!source_->ReadDeg(&raw)) {
      read_failures_++;
      return false;
    }
    window_[head_] = raw;
    head_ = static_cast<uint8_t>((head_ + 1) % kN);
    if (filled_ < kN) filled_++;
    const float filtered = Average();  // 循环窗口均值（角度域，跨 0 点时取最短差平均）
    if (has_last_ && fabsf(ShortestAngleDiff(filtered, last_deg_)) > cfg_.jitter_warn_deg) {
      jitter_events_++;
    }
    last_deg_ = filtered;
    has_last_ = true;
    *out_deg = Normalize360(filtered - cfg_.zero_offset_deg);
    return true;
  }

 private:
  static constexpr uint8_t kN = 8;
  static float Normalize360(float deg) {
    float v = fmodf(deg, 360.0f);
    if (v < 0.0f) v += 360.0f;
    return v;
  }
  static float ShortestAngleDiff(float a, float b) {
    float d = Normalize360(a) - Normalize360(b);
    if (d > 180.0f) d -= 360.0f;
    if (d <= -180.0f) d += 360.0f;
    return d;
  }
  float Average() const {
    const uint8_t n = (cfg_.filter_window == 0 || cfg_.filter_window == 1) ? 1 : filled_;
    if (n <= 1) return window_[(head_ + kN - 1) % kN];
    // 以最后一个样本为基准做最短差平均（避免跨 0 点把 359 与 1 平均成 180）
    const float ref = window_[(head_ + kN - 1) % kN];
    float sum = 0.0f;
    uint8_t used = 0;
    const uint8_t window = (cfg_.filter_window < n) ? cfg_.filter_window : n;
    for (uint8_t i = 0; i < window; i++) {
      const float sample = window_[(head_ + kN - 1 - i) % kN];
      sum += ShortestAngleDiff(sample, ref);
      used++;
    }
    return Normalize360(ref + (used ? sum / used : 0.0f));
  }

  AngleSource* source_ = nullptr;
  Config cfg_{};
  float window_[kN] = {0.0f};
  uint8_t head_ = 0;
  uint8_t filled_ = 0;
  float last_deg_ = 0.0f;
  bool has_last_ = false;
  uint32_t read_failures_ = 0;
  uint32_t jitter_events_ = 0;
};

//: 自校准 / 归零结果
struct CalibrationReport {
  bool ok = false;
  float min_deg = 0.0f;          // 行程下限（回读值）
  float max_deg = 0.0f;          // 行程上限
  float span_deg = 0.0f;         // 实测行程
  float max_residual_deg = 0.0f;  // 相对理想线性的最大偏差（非线性指标）
  uint32_t samples = 0;
  uint32_t jitter_events = 0;
  uint32_t read_failures = 0;
  char note[64] = {0};
};

//: 闭环 + 校准控制器（位置误差 → 微调建议；归零/自校准产出报告）
class ClosedLoopController {
 public:
  struct Config {
    float tolerance_deg = 0.5f;    // 位置误差容限
    float max_trim_deg = 3.0f;     // 单次微调上限（防振荡）
    float step_timeout_s = 20.0f;  // 回零/校准单步超时
    float slow_speed_deg_s = 3.0f; // 归零/校准扫描速度
  };

  explicit ClosedLoopController(As5600Reader* reader) : reader_(reader) {}
  ClosedLoopController(As5600Reader* reader, const Config& cfg) : reader_(reader), cfg_(cfg) {}

  const Config& config() const { return cfg_; }
  const CalibrationReport& last_report() const { return report_; }
  bool homed() const { return homed_; }
  float zero_offset_deg() const { return zero_offset_deg_; }

  //: 闭环微调建议：目标与实测之差超过容限时给出带符号的修正量（限幅）
  bool TrimRecommendation(float target_deg, float* out_trim_deg) {
    float measured = 0.0f;
    if (reader_ == nullptr || !reader_->ReadDeg(&measured)) return false;
    float error = ShortestDelta(target_deg, measured);
    if (fabsf(error) <= cfg_.tolerance_deg) {
      if (out_trim_deg) *out_trim_deg = 0.0f;
      return false;
    }
    // 修正方向 = 从「实测」走到「目标」的有向最短差（trim 加到实测角上）
    // 注意别取反：写成 -error 会让云台越修越偏（主机端规格测试抓到过）
    float trim = error;
    if (trim > cfg_.max_trim_deg) trim = cfg_.max_trim_deg;
    if (trim < -cfg_.max_trim_deg) trim = -cfg_.max_trim_deg;
    if (out_trim_deg) *out_trim_deg = trim;
    return true;
  }

  //: 归零：把当前位置记为零点（真机上是「慢速扫到标记位」后调用），返回是否可持久化
  bool CalibrateZeroHere(float measured_deg, float* out_offset_deg) {
    if (!isfinite(measured_deg)) return false;
    zero_offset_deg_ = Normalize360(measured_deg);
    if (reader_ != nullptr) reader_->set_zero_offset(zero_offset_deg_);
    homed_ = true;
    if (out_offset_deg) *out_offset_deg = zero_offset_deg_;
    return true;
  }

  //: 自校准：往返扫描采样 → 行程两端 + 非线性残差 + 抖动/读失败统计
  //:   sweep: 依次喂入的采样角度（真机由运动层扫出，测试由合成源给出）
  CalibrationReport SelfCalibrate(const float* sweep_deg, uint32_t count) {
    CalibrationReport rep;
    if (reader_ == nullptr || sweep_deg == nullptr || count < 4) {
      snprintf(rep.note, sizeof(rep.note), "样本不足");
      return rep;
    }
    float min_deg = 360.0f, max_deg = 0.0f;
    float sum_x = 0.0f, sum_y = 0.0f, sum_xx = 0.0f, sum_xy = 0.0f;
    for (uint32_t i = 0; i < count; i++) {
      const float index_deg = Normalize360(sweep_deg[i]);      // 理想值（按索引进度）
      float measured = 0.0f;
      if (!reader_->ReadDeg(&measured)) {
        rep.read_failures++;
        continue;
      }
      measured = Normalize360(measured);
      if (measured < min_deg) min_deg = measured;
      if (measured > max_deg) max_deg = measured;
      const float x = index_deg, y = measured;
      sum_x += x; sum_y += y; sum_xx += x * x; sum_xy += x * y;
      rep.samples++;
    }
    if (rep.samples < 4) {
      snprintf(rep.note, sizeof(rep.note), "有效样本不足");
      return rep;
    }
    const float n = static_cast<float>(rep.samples);
    const float denom = n * sum_xx - sum_x * sum_x;
    const float slope = (fabsf(denom) > 1e-6f) ? ((n * sum_xy - sum_x * sum_y) / denom) : 1.0f;
    const float intercept = (sum_y - slope * sum_x) / n;
    // 残差：实测相对拟合直线的最大偏差（非线性/畸变指标）
    float max_residual = 0.0f;
    for (uint32_t i = 0; i < count; i++) {
      float measured = 0.0f;
      if (!reader_->ReadDeg(&measured)) continue;  // 第二次读（真机上即再采样一次）
      const float ideal = slope * Normalize360(sweep_deg[i]) + intercept;
      const float residual = fabsf(ShortestDelta(ideal, Normalize360(measured)));
      if (residual > max_residual) max_residual = residual;
    }
    rep.ok = true;
    rep.min_deg = min_deg;
    rep.max_deg = max_deg;
    rep.span_deg = max_deg - min_deg;
    rep.max_residual_deg = max_residual;
    rep.jitter_events = reader_->jitter_events();
    if (rep.max_residual_deg > 1.0f) {
      snprintf(rep.note, sizeof(rep.note), "非线性偏大(%.2f°)，建议检查磁铁偏心", rep.max_residual_deg);
    } else {
      snprintf(rep.note, sizeof(rep.note), "校准正常");
    }
    report_ = rep;
    return rep;
  }

 private:
  static float Normalize360(float deg) {
    float v = fmodf(deg, 360.0f);
    if (v < 0.0f) v += 360.0f;
    return v;
  }
  static float ShortestDelta(float to_deg, float from_deg) {
    float d = Normalize360(to_deg) - Normalize360(from_deg);
    if (d > 180.0f) d -= 360.0f;
    if (d <= -180.0f) d += 360.0f;
    return d;
  }

  As5600Reader* reader_ = nullptr;
  Config cfg_{};
  CalibrationReport report_{};
  float zero_offset_deg_ = 0.0f;
  bool homed_ = false;
};

}  // namespace antenna
