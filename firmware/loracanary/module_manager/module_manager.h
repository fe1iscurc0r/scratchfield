/* LoRaCanary · 模块管理器（SkillForge 授粉 → 固件模块验证 + 自动回滚）。
 *
 * 背景（digest-g2-3 SkillForge 授粉点，2608.24747v1）：
 *   SkillForge 的「技能银行通过环境交互持续验证 + 证据引导归纳」迁移到固件层：
 *   —— 固件模块在运行时通过环境交互（硬件状态反馈）验证自身正确性，
 *     失效模块触发自动回滚到上一版本，而非整机重刷。
 *
 * 设计边界（诚实标注）：
 *   - 本骨架是纯逻辑状态机（无 Arduino 依赖，可在主机 g++ 编译），负责
 *     「自检评分 → 连续失败计数 → 回滚决策 → A/B 槽位切换」的判定与状态推进。
 *   - 硬件反馈读取（ADC 电压、SPI/I2C 应答、SX1278 RSSI、看门狗复位计数）由
 *     各模块的自检回调函数实现，回调把 HardwareFeedback 映射成 0..100 健康分。
 *   - 真正的分区擦写/跳转（esp_ota_set_boot_partition / 双 app 分区）在 ESP-IDF
 *     层执行，本层只输出「回滚哪个模块、切到哪个槽位」的决策结果。
 *   - 与 AA/AB 线既有固件兼容：不改 loracanary_frame 帧协议、不改 node_config。
 *
 * 触发条件表见 docs/loracanary-module-ota-方案.md（本头文件只是运行载体）。
 */
#ifndef LORACANARY_MODULE_MANAGER_H
#define LORACANARY_MODULE_MANAGER_H

#include <stdint.h>

#include <functional>
#include <string>
#include <vector>

namespace loracanary {
namespace mm {

// 单次自检低于该分数视为「本次不合格」，计入连续失败计数。
constexpr int kPassThreshold = 50;

// 模块健康度（运行时环境交互验证的结果分档）
enum class Health {
  UNKNOWN = 0,  // 未自检
  HEALTHY = 1,  // 合格（>= kPassThreshold）
  DEGRADED = 2, // 边缘（保留但计数）
  FAILED = 3,   // 不合格（< kPassThreshold）
};

// 模块生命周期状态机
enum class ModuleState {
  INACTIVE = 0,    // 未激活（禁用/占位）
  ACTIVE = 1,      // 运行中
  FAILED = 2,      // 连续失败已达阈值，待回滚
  ROLLED_BACK = 3, // 已回滚到上一版本
  QUARANTINED = 4, // 回滚后仍失败，隔离（不再参与运行）
};

// 硬件状态反馈：模块自检的输入。各模块按需取用字段，未接外设的字段保持默认
// 「健康」语义，由自检回调决定权重。缺失外设（如未接 MOS 电源控制）不会误判。
struct HardwareFeedback {
  bool power_ok = true;           // 供电轨正常（ADC 电压在窗内）
  bool spi_ok = true;             // SPI 器件应答
  bool i2c_ok = true;             // I2C 器件应答
  bool gpio_ok = true;            // 关键 GPIO 电平符合预期
  float vcc_mv = 3300.0f;         // 实测供电电压
  int rssi_dbm = -60;             // RF 模块回报（SX1278：-127..0）
  uint32_t bus_error_count = 0;   // 总线错误累计（周期内）
  uint32_t watchdog_resets = 0;   // 看门狗复位累计
};

// 模块版本：A/B 槽位共存（slot 0/1 对应双分区）。
struct ModuleVersion {
  uint16_t major = 1;
  uint16_t minor = 0;
  uint8_t slot = 0;

  bool operator==(const ModuleVersion &o) const {
    return major == o.major && minor == o.minor && slot == o.slot;
  }
};

// 自检回调：把一次硬件反馈映射成健康评分 0..100（0=完全失效）。
// 返回 < kPassThreshold 记为一次不合格。
using SelfCheckFn = std::function<int(const HardwareFeedback &)>;

// 模块描述符：注册到管理器的元数据 + 运行期状态。
struct ModuleDescriptor {
  std::string id;               // 模块唯一 id（如 "rf" / "gps" / "bme"）
  ModuleVersion active;         // 当前激活版本（槽位）
  ModuleVersion prev;           // 回滚目标（上一已知良好版本）
  SelfCheckFn self_check;       // 自检回调（可为空 = 恒健康，仅登记不体检）
  int fail_threshold = 3;       // 连续失败多少次触发回滚

  // 运行期状态（由 ModuleManager 维护）
  int health_score = 0;         // 最近一次自检评分
  int consecutive_fails = 0;    // 连续不合格计数
  ModuleState state = ModuleState::ACTIVE;
  uint32_t epoch = 0;           // 模块生命周期计数（每次回滚 +1）
};

// 一次回滚决策的结果：回滚了哪些模块、隔离了哪些模块。
struct RollbackDecision {
  std::vector<std::string> rolled;       // 本次回滚（ACTIVE→ROLLED_BACK）
  std::vector<std::string> quarantined;  // 本次隔离（ROLLED_BACK 仍连续失败）
};

// 模块管理器：自检评分 + 连续失败推进 + 回滚/隔离决策（不整机重刷）。
class ModuleManager {
 public:
  // 登记一个模块（重复 id 忽略，不覆盖，防止误注册双份）。
  void register_module(const ModuleDescriptor &m);

  // 运行期健康检查：对每个模块跑一次自检，推进健康分与连续失败计数。
  void run_health_check(const HardwareFeedback &fb);

  // 按触发条件表执行回滚/隔离决策；返回本次结果（可能两列表都为空）。
  RollbackDecision evaluate_and_rollback();

  // 强制回滚单个模块到 prev 槽位（不整体重刷）；失败返回 false。
  bool rollback(const std::string &id);

  // 隔离单个模块（停止参与体检与再回滚，防止回滚抖动）；失败返回 false。
  bool quarantine(const std::string &id);

  // 查询 / 快照。
  const ModuleDescriptor *find(const std::string &id) const;
  std::vector<ModuleDescriptor> snapshot() const;

  static const char *state_name(ModuleState s);

 private:
  ModuleDescriptor *find_mut(const std::string &id);
  std::vector<ModuleDescriptor> modules_;
};

}  // namespace mm
}  // namespace loracanary

#endif /* LORACANARY_MODULE_MANAGER_H */
