// 天线云台 · 运动层自检（卷129 W129-01）
//
// 编译：arduino-cli compile --fqbn esp32:esp32:esp32s3 hardware/antenna-rotator
// 上机：串口 115200，输出 [SELFTEST] 行；全通过打印 SELFTEST_PASS，任一失败 SELFTEST_FAIL
//
// 自检覆盖（对应工单验收）：
//  1. 单轴 move 30° 的梯形剖面（加速/匀速/减速时序与位移闭合）
//  2. 方位最短路径 355°→5° 应走 +10°（不是 -350°）
//  3. 软限位越限拒绝（俯仰 120° 被拒且状态不动）
//  4. 状态机迁移 idle→accel→cruise→decel→done
//  5. 参数非法（速度/加速度非正）拒绝为 invalid
#include <Arduino.h>

#include "cmd/cmd_parser.hpp"
#include "feedback/as5600.hpp"
#include "motion/planner.hpp"
#include "servo_ptz/servo_axis.hpp"

namespace {

int g_failures = 0;

void Check(bool ok, const char* name) {
  Serial.printf("[SELFTEST] %-38s %s\n", name, ok ? "PASS" : "FAIL");
  if (!ok) g_failures++;
}

//: 用固定步长推进到结束，返回是否到达且位移闭合
bool RunToCompletion(antenna::Planner& planner, float step_s, float* out_deg,
                     antenna::MotionState* out_state, int* steps) {
  int guard = 0;
  const int kMaxSteps = 100000;
  while (planner.moving() && guard++ < kMaxSteps) {
    planner.Step(step_s);
  }
  if (out_deg) *out_deg = planner.current_deg();
  if (out_state) *out_state = planner.state();
  if (steps) *steps = guard;
  return guard < kMaxSteps;
}

void TestTrapezoidProfile() {
  antenna::PlannerConfig cfg;
  antenna::Planner planner(cfg);
  planner.ResetTo(0.0f);
  const auto result = planner.PlanMove(30.0f, 10.0f, 5.0f);
  Check(result == antenna::PlanResult::kOk, "move 30deg 规划通过");

  const auto& profile = planner.profile();
  // 30° @ v=10, a=5 → 加速 2s 走 10°，减速 2s 走 10°，匀速 1s 走 10°（三段）
  const bool has_three = profile.segment_count == 3;
  const bool accel_phase = profile.segments[0].phase == antenna::MotionState::kAccel;
  const bool cruise_phase = profile.segments[1].phase == antenna::MotionState::kCruise;
  const bool decel_phase = profile.segments[2].phase == antenna::MotionState::kDecel;
  const bool timing = fabsf(profile.t_total_s - 5.0f) < 0.05f;
  const bool closed = fabsf(profile.segments[2].deg_end - 30.0f) < 0.05f;
  Serial.printf("[SELFTEST] 剖面：段=%u 总时长=%.2fs 位移闭合=%.2f°\n", profile.segment_count,
                profile.t_total_s, profile.segments[profile.segment_count - 1].deg_end);
  Check(has_three && accel_phase && cruise_phase && decel_phase, "剖面三段顺序 accel/cruise/decel");
  Check(timing, "总时长 ≈ 5.0s");
  Check(closed, "剖面位移闭合到 30°");

  float deg = 0.0f;
  antenna::MotionState state = antenna::MotionState::kIdle;
  int steps = 0;
  const bool finished = RunToCompletion(planner, 0.01f, &deg, &state, &steps);
  Check(finished && state == antenna::MotionState::kDone, "推进到 done");
  Check(fabsf(deg - 30.0f) < 0.2f, "终角 ≈ 30°");
}

void TestShortestPathAzimuth() {
  antenna::Planner planner;
  planner.ResetTo(355.0f);
  const auto result = planner.PlanMove(5.0f, 10.0f, 5.0f);
  const auto& profile = planner.profile();
  Serial.printf("[SELFTEST] 355→5 位移=%.2f°（期望 +10.00）\n", profile.delta_deg);
  Check(result == antenna::PlanResult::kOk, "355→5 规划通过");
  Check(fabsf(profile.delta_deg - 10.0f) < 0.05f, "最短路径 +10°（跨 0 点）");

  float deg = 0.0f;
  RunToCompletion(planner, 0.01f, &deg, nullptr, nullptr);
  Check(fabsf(deg - 5.0f) < 0.2f, "绕行后终角 ≈ 5°");
}

void TestSoftLimitReject() {
  antenna::Planner planner;
  planner.ResetTo(0.0f);
  const auto rejected = planner.PlanMove(120.0f, 10.0f, 5.0f, /*is_elevation=*/true);
  Serial.printf("[SELFTEST] 俯仰 120° 结果=%s 状态=%s 当前=%.2f°\n",
                antenna::ToString(rejected), antenna::ToString(planner.state()),
                planner.current_deg());
  Check(rejected == antenna::PlanResult::kRejectedLimit, "俯仰越限被拒（limit）");
  Check(!planner.moving(), "被拒后不产生运动");
  Check(fabsf(planner.current_deg() - 0.0f) < 1e-3f, "被拒后位置不变");

  const auto bad_speed = planner.PlanMove(10.0f, 0.0f, 5.0f);
  Check(bad_speed == antenna::PlanResult::kRejectedInvalid, "速度非正拒绝（invalid）");
}

void TestStateMachineTrace() {
  antenna::Planner planner;
  planner.ResetTo(0.0f);
  planner.PlanMove(90.0f, 20.0f, 10.0f);
  bool saw_accel = false, saw_cruise = false, saw_decel = false, saw_done = false;
  for (int i = 0; i < 20000 && planner.moving(); i++) {
    planner.Step(0.005f);
    switch (planner.state()) {
      case antenna::MotionState::kAccel: saw_accel = true; break;
      case antenna::MotionState::kCruise: saw_cruise = true; break;
      case antenna::MotionState::kDecel: saw_decel = true; break;
      case antenna::MotionState::kDone: saw_done = true; break;
      default: break;
    }
  }
  planner.Step(0.005f);  // 触发 done
  saw_done = saw_done || planner.state() == antenna::MotionState::kDone;
  Serial.printf("[SELFTEST] 状态轨迹 accel=%d cruise=%d decel=%d done=%d\n", saw_accel, saw_cruise,
                saw_decel, saw_done);
  Check(saw_accel && saw_cruise && saw_decel && saw_done, "状态机迁移完整");
}

}  // namespace

// ---------------------------------------------------------------------------
// W129-02：AS5600 闭环 + 自校准（用合成源验证角度换算/滤波/归零/非线性检测）
// ---------------------------------------------------------------------------

namespace {

void TestEncoderConversion() {
  Check(fabsf(antenna::CountsToDeg(0) - 0.0f) < 1e-3f, "编码器 0 → 0°");
  Check(fabsf(antenna::CountsToDeg(2048) - 180.0f) < 0.05f, "编码器 2048 → 180°");
  Check(fabsf(antenna::CountsToDeg(4095) - 359.912f) < 0.05f, "编码器 4095 → ≈359.9°");
  Check(antenna::DegToCounts(90.0f) == 1024, "90° → 编码器 1024");
  Check(antenna::DegToCounts(-90.0f) == 3072, "−90° 归一化 → 3072");
}

void TestZeroOffsetAndFilter() {
  antenna::SyntheticSource source(4.0f);
  source.set_dt(0.0f);  // 固定不动，便于断言
  antenna::As5600Reader reader(&source);
  float deg = 0.0f;
  Check(reader.ReadDeg(&deg), "合成源读取成功");
  float offset = 0.0f;
  antenna::ClosedLoopController loop(&reader);
  Check(loop.CalibrateZeroHere(deg, &offset), "归零记录偏移");
  Check(loop.homed(), "归零状态置位");
  float after = 0.0f;
  Check(reader.ReadDeg(&after) && fabsf(after) < 1.0f, "去零点后读数 ≈ 0°（±1°）");

  // 抖动检测：注入 20° 跳变应被计数
  source.inject_step(20.0f);
  reader.ReadDeg(&after);
  Check(reader.jitter_events() >= 1, "跳变被记为 jitter 事件");
}

void TestReadFailureSurfaced() {
  antenna::SyntheticSource source(4.0f);
  source.fail_next(1);
  antenna::As5600Reader reader(&source);
  float deg = 0.0f;
  Check(!reader.ReadDeg(&deg), "I2C 读失败被如实上报（不吞错）");
  Check(reader.read_failures() == 1, "读失败计数 +1");
}

void TestSelfCalibrationReport() {
  antenna::SyntheticSource source(4.0f);
  source.set_dt(0.02f);
  antenna::As5600Reader reader(&source);
  float sweep[64];
  for (int i = 0; i < 64; i++) sweep[i] = (360.0f / 64.0f) * i;  // 理想扫角
  antenna::ClosedLoopController loop(&reader);
  const auto rep = loop.SelfCalibrate(sweep, 64);
  Serial.printf("[SELFTEST] 校准：samples=%u 行程=%.1f° 最大残差=%.2f° note=%s\n", rep.samples,
                rep.span_deg, rep.max_residual_deg, rep.note);
  Check(rep.ok && rep.samples >= 4, "自校准产出报告");
  Check(rep.span_deg > 100.0f, "扫描行程被记录");
  Check(rep.max_residual_deg >= 0.0f, "非线性残差被量化");
}

}  // namespace

// ---------------------------------------------------------------------------
// W129-03：舵机 PTZ（平滑渐变 / 限位 / 群控 / 堵转 fault）
// ---------------------------------------------------------------------------

namespace {

void TestServoCalibration() {
  antenna::ServoCalibration cal;
  Check(cal.DegToUs(0.0f) == 500, "0° → 500us");
  Check(cal.DegToUs(180.0f) == 2500, "180° → 2500us");
  Check(cal.DegToUs(90.0f) == 1500, "90° → 1500us");
  Check(cal.DegToUs(-20.0f) == 500, "下限外被夹到 500us");
  Check(cal.DegToUs(400.0f) == 2500, "上限外被夹到 2500us");
}

void TestSmoothGradientNoJump() {
  antenna::ServoCalibration cal;
  antenna::RecordingServoOutput out;
  antenna::ServoAxis axis(1, &out, cal);
  axis.Attach(0.0f);
  const char* reason = nullptr;
  Check(axis.SetTarget(60.0f, &reason), "设定目标 60° 通过");

  float last = 0.0f;
  float max_step = 0.0f;
  int ticks = 0;
  while (axis.Tick() && ticks < 1000) {
    const float step = fabsf(axis.current_deg() - last);
    if (step > max_step) max_step = step;
    last = axis.current_deg();
    ticks++;
  }
  Serial.printf("[SELFTEST] 舵机渐变：ticks=%d 最大单步=%.2f° 写入=%u 次\n", ticks, max_step,
                out.writes());
  Check(max_step <= 2.5001f, "单步不超 2.5°（无突跳）");
  Check(ticks == 24, "60° / 2.5° = 24 个节拍");
  Check(fabsf(axis.current_deg() - 60.0f) < 1e-3f, "终角到位");
  Check(!axis.moving(), "到位后状态为非运动");
}

void TestServoLimitAndStall() {
  antenna::ServoCalibration cal;
  antenna::RecordingServoOutput out;
  antenna::ServoAxis axis(1, &out, cal);
  axis.Attach(0.0f);
  const char* reason = nullptr;
  Check(!axis.SetTarget(200.0f, &reason), "200° 越限被拒");
  Check(reason != nullptr && strcmp(reason, "limit") == 0, "拒绝原因是 limit");
  Check(axis.Status().fault, "被拒后 fault 置位");
  Check(fabsf(axis.current_deg()) < 1e-6f, "被拒后位置不变");
  axis.ClearFault();

  antenna::ServoAxis::Config cfg;
  cfg.stall_current_a = 1.2f;
  antenna::ServoAxis guarded(2, &out, cal, cfg);
  guarded.Attach(10.0f);
  Check(guarded.SampleCurrent(0.5f), "电流正常不触发");
  Check(!guarded.SampleCurrent(1.8f), "电流超阈值触发堵转");
  Check(guarded.Status().fault, "堵转后 fault 置位");
  guarded.SetTarget(20.0f);
  guarded.Tick();
  Check(guarded.Status().fault, "fault 状态下不再动作（Tick 不推进）");
}

void TestMultiAxisParallel() {
  antenna::ServoCalibration cal;
  antenna::RecordingServoOutput out_pan, out_tilt;
  antenna::ServoAxis pan(1, &out_pan, cal);
  antenna::ServoAxis tilt(2, &out_tilt, cal);
  pan.Attach(10.0f);
  tilt.Attach(10.0f);
  antenna::PtzManager ptz;
  Check(ptz.Add(&pan) && ptz.Add(&tilt), "注册两轴");
  const float targets[2] = {100.0f, 40.0f};
  Check(ptz.MoveAll(targets, 2), "并行设定目标");
  const bool done = ptz.RunToTargets(3000, 20);
  Serial.printf("[SELFTEST] 两轴并行：pan=%.1f° tilt=%.1f° 到位=%d\n", pan.current_deg(),
                tilt.current_deg(), done);
  Check(done, "两轴均到位（未超时）");
  Check(fabsf(pan.current_deg() - 100.0f) < 0.01f && fabsf(tilt.current_deg() - 40.0f) < 0.01f,
        "两轴终角正确");
  Check(ptz.Status(0).moving == false && ptz.Status(1).moving == false, "状态上报 moving=false");
}

}  // namespace

// ---------------------------------------------------------------------------
// W129-04：G 代码命令面（解析 + 直线插补 + 内存 REPL 往返）
// ---------------------------------------------------------------------------

namespace {

//: 内存传输（自检用）：预置输入行，收集输出行
class MemoryTransport : public antenna::ReplTransport {
 public:
  void Push(const char* line) {
    if (in_count_ < kMax) snprintf(input_[in_count_++], sizeof(input_[0]), "%s", line);
  }
  bool ReadLine(char* out, size_t max_len) override {
    if (read_index_ >= in_count_) return false;
    snprintf(out, max_len, "%s", input_[read_index_++]);
    return true;
  }
  void WriteLine(const char* text) override {
    if (out_count_ < kMax) snprintf(output_[out_count_++], sizeof(output_[0]), "%s", text);
  }
  const char* Output(uint32_t i) const { return (i < out_count_) ? output_[i] : ""; }
  uint32_t output_count() const { return out_count_; }

 private:
  static constexpr uint32_t kMax = 16;
  char input_[kMax][96] = {{0}};
  char output_[kMax][96] = {{0}};
  uint32_t in_count_ = 0, read_index_ = 0, out_count_ = 0;
};

//: 命令面 sink：记录动作（自检不需要真驱动电机）
class RecordingSink : public antenna::MotionCommandSink {
 public:
  const char* MoveTo(float az, float el, float feed, bool linear) override {
    last_az_ = az;
    last_el_ = el;
    last_feed_ = feed;
    last_linear_ = linear;
    moves_++;
    if (!isnan(az) && (az < 0.0f || az > 360.0f)) return "error:limit";
    return nullptr;
  }
  const char* Home() override {
    homes_++;
    return nullptr;
  }
  void Hold(float seconds) override { last_hold_ = seconds; }
  void Enable(bool on) override { enabled_ = on; }
  const char* StatusLine(char* out, size_t max_len) override {
    snprintf(out, max_len, "az=%.2f el=%.2f moving=0 fault=0 enabled=%d", last_az_, last_el_,
             enabled_ ? 1 : 0);
    return nullptr;
  }
  float last_az_ = 0.0f, last_el_ = 0.0f, last_feed_ = 0.0f, last_hold_ = 0.0f;
  bool last_linear_ = false, enabled_ = false;
  int moves_ = 0, homes_ = 0;
};

void TestGcodeParsing() {
  const auto fast = antenna::ParseGcode("G0 X30 Y-10 F5");
  Check(fast.ok && fast.id == antenna::GcodeId::kG0, "解析 G0");
  Check(fabsf(fast.x - 30.0f) < 1e-3f && fabsf(fast.y + 10.0f) < 1e-3f, "解析 X/Y 数值");
  Check(fabsf(fast.f - 5.0f) < 1e-3f, "解析 F 速度");

  const auto line = antenna::ParseGcode("g1 x12.5 f8 ; 注释");
  Check(line.ok && line.id == antenna::GcodeId::kG1, "小写 + 注释可解析");

  const auto query = antenna::ParseGcode("M114");
  Check(query.ok && query.id == antenna::GcodeId::kM114, "解析 M114");

  const auto hold = antenna::ParseGcode("G4 P1.5");
  Check(hold.ok && hold.id == antenna::GcodeId::kG4 && fabsf(hold.p - 1.5f) < 1e-3f, "解析 G4 P");

  const auto unknown = antenna::ParseGcode("G99");
  Check(!unknown.ok && strstr(unknown.error, "unsupported") != nullptr, "未知 G 码报 unsupported");
  const auto garbage = antenna::ParseGcode("hello");
  Check(!garbage.ok && strcmp(garbage.error, "unknown") == 0, "非 G 码报 unknown");
}

void TestLinearInterpolationRatio() {
  // 行程 90°/30°、F=30°/s → 时长 3s；慢轴按比例降速（两轴同时到达）
  const auto plan = antenna::PlanLinear(90.0f, 30.0f, 30.0f);
  Serial.printf("[SELFTEST] 插补：va=%.2f ve=%.2f dur=%.2fs\n", plan.v_az_deg_s, plan.v_el_deg_s,
                plan.duration_s);
  Check(plan.ok, "插补计划生成");
  Check(fabsf(plan.duration_s - 3.0f) < 1e-3f, "时长 = 最长行程 / F");
  Check(fabsf(plan.v_az_deg_s - 30.0f) < 1e-3f, "方位轴全速（最长行程）");
  Check(fabsf(plan.v_el_deg_s - 10.0f) < 1e-3f, "俯仰轴按比例降速（30/3=10）");
  const auto bad = antenna::PlanLinear(0.0f, 0.0f, 10.0f);
  Check(!bad.ok, "零位移不产生插补计划");
}

void TestReplRoundTrip() {
  RecordingSink sink;
  antenna::CommandInterpreter interp(&sink);
  MemoryTransport transport;
  transport.Push("M17");
  transport.Push("G0 X30 Y10 F5");
  transport.Push("G4 P2");
  transport.Push("M114");
  transport.Push("G28");
  transport.Push("G99 X1");
  const uint32_t handled = interp.Poll(&transport);
  Check(handled == 6, "六条命令均被处理");
  Check(strcmp(transport.Output(0), "ok") == 0, "M17 → ok");
  Check(strcmp(transport.Output(1), "ok") == 0, "G0 → ok");
  Check(strcmp(transport.Output(2), "ok") == 0, "G4 → ok");
  Check(strstr(transport.Output(3), "az=30.00") != nullptr, "M114 回状态行");
  Check(sink.moves_ == 1 && sink.homes_ == 1, "sink 收到 move/home");
  Check(fabsf(sink.last_hold_ - 2.0f) < 1e-3f && sink.enabled_, "hold 与 enable 生效");
  Check(strstr(transport.Output(5), "error:") != nullptr, "未知命令 error 回显");

  // 越限：G0 X400 → sink 返回 error:limit
  MemoryTransport limit_t; 
  limit_t.Push("G0 X400");
  interp.Poll(&limit_t);
  Check(strcmp(limit_t.Output(0), "error:limit") == 0, "越限回显 error:limit");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("[SELFTEST] antenna-rotator motion planner (W129-01)");
  TestTrapezoidProfile();
  TestShortestPathAzimuth();
  TestSoftLimitReject();
  TestStateMachineTrace();
  Serial.println("[SELFTEST] AS5600 closed loop (W129-02)");
  TestEncoderConversion();
  TestZeroOffsetAndFilter();
  TestReadFailureSurfaced();
  TestSelfCalibrationReport();
  Serial.println("[SELFTEST] Servo PTZ (W129-03)");
  TestServoCalibration();
  TestSmoothGradientNoJump();
  TestServoLimitAndStall();
  TestMultiAxisParallel();
  Serial.println("[SELFTEST] G-code command face (W129-04)");
  TestGcodeParsing();
  TestLinearInterpolationRatio();
  TestReplRoundTrip();
  Serial.printf("[SELFTEST] failures=%d\n", g_failures);
  Serial.println(g_failures == 0 ? "SELFTEST_PASS" : "SELFTEST_FAIL");
}

void loop() {
  delay(2000);
  Serial.println(g_failures == 0 ? "SELFTEST_PASS" : "SELFTEST_FAIL");
}
