// 运动规划核心（卷129 W129-01）——双轴角度域加减速规划，平台无关 C++（ESP32 上用，也能被测试桩调用）
//
// 授粉参考（机制，不整抄）：GRBL 的 `st_` 状态机 + 分段规划、Marlin 的分段加减速与 jerk 限制、
// AccelStepper 的 step 级加减速。本文件只实现角度域语义（云台用度，不用步）。
//
// 核心概念
// --------
// - **度制优先**：输入 0-360° 方位 / ±90° 俯仰；`PlanMove` 输出速度剖面（加速→匀速→减速）
// - **最短路径绕行**：355°→5° 走 +10°（跨 0 点），而不是 -350°
// - **软限位**：越限直接 `REJECTED`，不产生任何运动
// - **状态机**：IDLE → ACCEL → CRUISE → DECEL → DONE（异常 → FAULT）
//
// 本文件不依赖 Arduino API（除了 millis/micros 的注入式时钟），便于主机端与固件端共用。
#pragma once

#include <cmath>
#include <cstdint>

namespace antenna {

//: 规划状态机（与 GRBL 的 state 语义对齐，命名自定）
enum class MotionState : uint8_t {
  kIdle = 0,
  kAccel,
  kCruise,
  kDecel,
  kDone,
  kFault,
};

enum class PlanResult : uint8_t {
  kOk = 0,
  kRejectedLimit,    // 越限拒绝（软限位）
  kRejectedInvalid,  // 参数非法（速度/加速度非正、NaN 等）
  kFault,            // 内部故障（数值异常）
};

const char* ToString(MotionState state) {
  switch (state) {
    case MotionState::kIdle: return "idle";
    case MotionState::kAccel: return "accel";
    case MotionState::kCruise: return "cruise";
    case MotionState::kDecel: return "decel";
    case MotionState::kDone: return "done";
    case MotionState::kFault: return "fault";
  }
  return "unknown";
}

const char* ToString(PlanResult result) {
  switch (result) {
    case PlanResult::kOk: return "ok";
    case PlanResult::kRejectedLimit: return "rejected:limit";
    case PlanResult::kRejectedInvalid: return "rejected:invalid";
    case PlanResult::kFault: return "fault";
  }
  return "unknown";
}

//: 单轴限位（度）。方位轴通常 0..360，俯仰 -90..90。
struct AxisLimits {
  float min_deg;
  float max_deg;
};

//: 把角度归一化到 [0, 360)
inline float NormalizeDeg360(float deg) {
  float v = std::fmod(deg, 360.0f);
  if (v < 0.0f) v += 360.0f;
  return v;
}

//: 方位角最短路径：返回带符号的有向角差（-180, 180]，正为顺时针
inline float ShortestDeltaDeg(float from_deg, float to_deg) {
  float delta = NormalizeDeg360(to_deg) - NormalizeDeg360(from_deg);
  if (delta > 180.0f) delta -= 360.0f;
  if (delta <= -180.0f) delta += 360.0f;
  return delta;
}

//: 梯形/S 曲线速度剖面的一段（绝对时间轴，单位秒）
struct ProfileSegment {
  float t_start_s;
  float t_end_s;
  float v_start_deg_s;
  float v_end_deg_s;
  float deg_start;  // 该段起点的**相对位移**（度，相对本次 move 起点）
  float deg_end;
  MotionState phase;
};

//: 一次 move 的完整剖面（最多 3 段：加速/匀速/减速；S 曲线模式按 jerk 再细分阶段但只报 3 段包络）
struct MotionProfile {
  PlanResult result = PlanResult::kRejectedInvalid;
  float delta_deg = 0.0f;       // 带符号位移（最短路径后）
  float v_peak_deg_s = 0.0f;    // 实际峰值速度（可能低于设定，若行程太短）
  float t_total_s = 0.0f;       // 总时长
  uint8_t segment_count = 0;
  ProfileSegment segments[3];
  bool s_curve = false;
};

//: 规划器参数
struct PlannerConfig {
  AxisLimits azimuth{0.0f, 360.0f};  // 方位软限位（度）
  AxisLimits elevation{-90.0f, 90.0f};
  float azimuth_wrap = true;         // 方位是否按最短路径绕行（跨 0 点）
  float jerk_deg_s3 = 0.0f;          // S 曲线 jerk 上限（0 = 不启用 S 曲线）
  float min_speed_deg_s = 0.05f;     // 低于此速度视为停止（防除零）
};

//: 单轴规划器：无动态分配、无浮点异常，可安全在 ISR 外调用
class Planner {
 public:
  explicit Planner(const PlannerConfig& cfg = PlannerConfig{}) : cfg_(cfg) {}

  const PlannerConfig& config() const { return cfg_; }
  void set_config(const PlannerConfig& cfg) { cfg_ = cfg; }

  MotionState state() const { return state_; }
  float current_deg() const { return current_deg_; }
  float target_deg() const { return target_deg_; }
  bool moving() const { return state_ == MotionState::kAccel || state_ == MotionState::kCruise ||
                               state_ == MotionState::kDecel; }

  //: 把当前位置直接设为某角（上电/回零后调用）
  PlanResult ResetTo(float deg) {
    if (!std::isfinite(deg)) return set_fault(PlanResult::kRejectedInvalid);
    current_deg_ = deg;
    target_deg_ = deg;
    state_ = MotionState::kIdle;
    profile_ = MotionProfile{};
    return PlanResult::kOk;
  }

  //: 规划一次移动（只规划，不推进时间）
  //:   axis_kind: false=方位（可绕行、0..360 限位），true=俯仰（不可绕行、±90 限位）
  PlanResult PlanMove(float target_deg, float max_speed_deg_s, float accel_deg_s2,
                      bool is_elevation = false, bool use_s_curve = false) {
    if (!std::isfinite(target_deg) || !std::isfinite(max_speed_deg_s) ||
        !std::isfinite(accel_deg_s2) || max_speed_deg_s <= 0.0f || accel_deg_s2 <= 0.0f) {
      return set_fault(PlanResult::kRejectedInvalid);
    }
    const AxisLimits& limits = is_elevation ? cfg_.elevation : cfg_.azimuth;
    if (target_deg < limits.min_deg || target_deg > limits.max_deg) {
      // 越限拒绝：目标与状态都不动（三保险里的「软限位」）
      state_ = (state_ == MotionState::kIdle) ? MotionState::kIdle : MotionState::kFault;
      last_rejected_target_deg_ = target_deg;
      return PlanResult::kRejectedLimit;
    }

    float delta = target_deg - current_deg_;
    if (!is_elevation && cfg_.azimuth_wrap) {
      delta = ShortestDeltaDeg(current_deg_, target_deg);  // 355°→5° 走 +10°
    }
    const float distance = std::fabs(delta);

    MotionProfile profile;
    profile.delta_deg = delta;
    profile.s_curve = use_s_curve && cfg_.jerk_deg_s3 > 0.0f;
    if (distance < 1e-4f) {  // 已经在目标位置
      profile.result = PlanResult::kOk;
      profile.t_total_s = 0.0f;
      profile.segment_count = 0;
      profile_ = profile;
      target_deg_ = target_deg;
      state_ = MotionState::kDone;
      return PlanResult::kOk;
    }

    // 三角形 / 梯形判定：加速段与减速段各吃掉一半行程 → v_peak = √(a·d)
    // （写成 √(2ad) 会让加速段就跑完全程、三角剖面位移翻倍——主机端规格测试抓到过）
    const float v_accel_ideal = std::sqrt(accel_deg_s2 * distance);
    const float v_peak = std::fmin(max_speed_deg_s, v_accel_ideal);
    if (v_peak < cfg_.min_speed_deg_s) {
      return set_fault(PlanResult::kRejectedInvalid);
    }
    const float t_accel = v_peak / accel_deg_s2;
    const float d_accel = 0.5f * accel_deg_s2 * t_accel * t_accel;
    const float d_cruise = distance - 2.0f * d_accel;
    const float t_cruise = (d_cruise > 0.0f) ? (d_cruise / v_peak) : 0.0f;
    const float t_decel = t_accel;

    const float sign = (delta >= 0.0f) ? 1.0f : -1.0f;
    uint8_t n = 0;
    float t = 0.0f;
    float s = 0.0f;
    // 加速段
    profile.segments[n++] = MakeSegment(t, t + t_accel, 0.0f, v_peak * sign, s,
                                        s + d_accel * sign, MotionState::kAccel);
    t += t_accel;
    s += d_accel * sign;
    // 匀速段（存在才记）
    if (t_cruise > 0.0f) {
      profile.segments[n++] = MakeSegment(t, t + t_cruise, v_peak * sign, v_peak * sign, s,
                                          s + d_cruise * sign, MotionState::kCruise);
      t += t_cruise;
      s += d_cruise * sign;
    }
    // 减速段
    profile.segments[n++] =
        MakeSegment(t, t + t_decel, v_peak * sign, 0.0f, s, s + d_accel * sign, MotionState::kDecel);

    profile.result = PlanResult::kOk;
    profile.v_peak_deg_s = v_peak;
    profile.t_total_s = t_accel + t_cruise + t_decel;
    profile.segment_count = n;

    profile_ = profile;
    target_deg_ = target_deg;
    t_elapsed_ = 0.0f;
    current_start_deg_ = current_deg_;  // 记录本次 move 起点（Step 里据此换算绝对角）
    state_ = MotionState::kAccel;
    return PlanResult::kOk;
  }

  //: 按时间推进（dt 秒）。返回当前角度；到达目标返回 true 且状态转 DONE
  bool Step(float dt_s) {
    if (state_ != MotionState::kAccel && state_ != MotionState::kCruise &&
        state_ != MotionState::kDecel) {
      return state_ == MotionState::kDone;
    }
    if (!std::isfinite(dt_s) || dt_s < 0.0f) {
      set_fault(PlanResult::kRejectedInvalid);
      return false;
    }
    t_elapsed_ += dt_s;
    if (profile_.segment_count == 0 || t_elapsed_ >= profile_.t_total_s) {
      current_deg_ = target_deg_;
      state_ = MotionState::kDone;
      return true;
    }
    const ProfileSegment* seg = nullptr;
    for (uint8_t i = 0; i < profile_.segment_count; i++) {
      if (t_elapsed_ >= profile_.segments[i].t_start_s &&
          t_elapsed_ <= profile_.segments[i].t_end_s) {
        seg = &profile_.segments[i];
        break;
      }
    }
    if (seg == nullptr) {
      seg = &profile_.segments[profile_.segment_count - 1];  // 落在段边界时取最后一段
    }
    state_ = seg->phase;
    const float local_dt = t_elapsed_ - seg->t_start_s;
    const float v0 = seg->v_start_deg_s;
    const float a = (seg->phase == MotionState::kCruise)
                        ? 0.0f
                        : (seg->v_end_deg_s - seg->v_start_deg_s) /
                              std::fmax(1e-6f, seg->t_end_s - seg->t_start_s);
    const float local_s = v0 * local_dt + 0.5f * a * local_dt * local_dt;
    const float base = profile_.segments[0].deg_start;
    current_deg_ = current_start_deg_ + (seg->deg_start - base) + local_s;
    return false;
  }

  //: 当前速度（度/秒）——按剖面求值，便于上报
  float velocity_deg_s() const {
    if (state_ == MotionState::kDone || state_ == MotionState::kIdle) return 0.0f;
    for (uint8_t i = 0; i < profile_.segment_count; i++) {
      const ProfileSegment& seg = profile_.segments[i];
      if (t_elapsed_ >= seg.t_start_s && t_elapsed_ <= seg.t_end_s) {
        const float span = std::fmax(1e-6f, seg.t_end_s - seg.t_start_s);
        const float ratio = (t_elapsed_ - seg.t_start_s) / span;
        return seg.v_start_deg_s + (seg.v_end_deg_s - seg.v_start_deg_s) * ratio;
      }
    }
    return 0.0f;
  }

  const MotionProfile& profile() const { return profile_; }
  float last_rejected_target_deg() const { return last_rejected_target_deg_; }

 private:
  static ProfileSegment MakeSegment(float t0, float t1, float v0, float v1, float s0, float s1,
                                    MotionState phase) {
    ProfileSegment seg;
    seg.t_start_s = t0;
    seg.t_end_s = t1;
    seg.v_start_deg_s = v0;
    seg.v_end_deg_s = v1;
    seg.deg_start = s0;
    seg.deg_end = s1;
    seg.phase = phase;
    return seg;
  }

  PlanResult set_fault(PlanResult reason) {
    state_ = MotionState::kFault;
    return reason;
  }

  PlannerConfig cfg_{};
  MotionState state_ = MotionState::kIdle;
  MotionProfile profile_{};
  float current_deg_ = 0.0f;
  float current_start_deg_ = 0.0f;  // 本次 move 的起点（用于位移换算）
  float target_deg_ = 0.0f;
  float t_elapsed_ = 0.0f;
  float last_rejected_target_deg_ = 0.0f;
};

}  // namespace antenna
