/* LoRaCanary · 模块管理器实现（纯逻辑，主机可编译）。
 *
 * 与 module_manager.h 同源；无 Arduino 依赖，用于自检评分 / 连续失败推进 /
 * 回滚决策的状态机实现。ESP32 侧只替换「读取硬件反馈」的入口即可复用。
 */
#include "module_manager.h"

#include <algorithm>

namespace loracanary {
namespace mm {

void ModuleManager::register_module(const ModuleDescriptor &m) {
  // 重复 id 不覆盖：防止热插拔/重复登记把运行期状态重置掉。
  if (find_mut(m.id) != nullptr) {
    return;
  }
  ModuleDescriptor d = m;
  d.consecutive_fails = 0;
  d.health_score = 0;
  d.epoch = 0;
  if (m.self_check) {
    d.state = ModuleState::ACTIVE;
  } else {
    // 无自检回调 = 仅登记不体检，保持 INACTIVE，避免「无证据却判健康」。
    d.state = ModuleState::INACTIVE;
  }
  modules_.push_back(std::move(d));
}

void ModuleManager::run_health_check(const HardwareFeedback &fb) {
  for (auto &m : modules_) {
    if (!m.self_check) {
      continue;  // 无体检入口的模块不参与健康循环
    }
    if (m.state == ModuleState::QUARANTINED) {
      continue;  // 已隔离模块不再体检（避免反复触发）
    }
    m.health_score = m.self_check(fb);
    if (m.health_score < kPassThreshold) {
      m.consecutive_fails += 1;
    } else {
      m.consecutive_fails = 0;  // 一次合格即清零连续失败（滞回）
    }
  }
}

RollbackDecision ModuleManager::evaluate_and_rollback() {
  RollbackDecision d;
  for (auto &m : modules_) {
    if (m.consecutive_fails < m.fail_threshold) {
      continue;  // 未达阈值，不动作
    }
    if (m.state == ModuleState::ACTIVE) {
      // 连续失败达阈值 → 回滚到上一版本（不整机重刷）
      m.state = ModuleState::FAILED;
      if (rollback(m.id)) {
        d.rolled.push_back(m.id);
      }
    } else if (m.state == ModuleState::ROLLED_BACK) {
      // 回滚后仍连续失败 → 隔离，防止回滚抖动（触发条件表 T4）
      if (quarantine(m.id)) {
        d.quarantined.push_back(m.id);
      }
    }
    // 其余状态（INACTIVE/FAILED/QUARANTINED）不参与决策
  }
  return d;
}

bool ModuleManager::quarantine(const std::string &id) {
  ModuleDescriptor *m = find_mut(id);
  if (m == nullptr) {
    return false;
  }
  m->state = ModuleState::QUARANTINED;
  m->consecutive_fails = 0;  // 隔离后清零，停止滚动
  return true;
}

bool ModuleManager::rollback(const std::string &id) {
  ModuleDescriptor *m = find_mut(id);
  if (m == nullptr) {
    return false;
  }
  // 无 prev 可回滚（单版本）或已隔离 → 拒绝，避免空回滚。
  if (m->state == ModuleState::QUARANTINED) {
    return false;
  }
  if (m->active == m->prev) {
    // 上一版本与当前一致 = 没有可回滚目标。置 FAILED 后由上层决定是否隔离。
    m->state = ModuleState::FAILED;
    return false;
  }

  // 执行 A/B 槽位切换：当前版本降到 prev，prev 记为「旧激活」（保留证据）。
  ModuleVersion old_active = m->active;
  m->active = m->prev;
  m->prev = old_active;
  m->consecutive_fails = 0;
  m->state = ModuleState::ROLLED_BACK;
  m->epoch += 1;
  return true;
}

const ModuleDescriptor *ModuleManager::find(const std::string &id) const {
  for (const auto &m : modules_) {
    if (m.id == id) {
      return &m;
    }
  }
  return nullptr;
}

ModuleDescriptor *ModuleManager::find_mut(const std::string &id) {
  for (auto &m : modules_) {
    if (m.id == id) {
      return &m;
    }
  }
  return nullptr;
}

std::vector<ModuleDescriptor> ModuleManager::snapshot() const {
  return modules_;
}

const char *ModuleManager::state_name(ModuleState s) {
  switch (s) {
    case ModuleState::INACTIVE:    return "INACTIVE";
    case ModuleState::ACTIVE:      return "ACTIVE";
    case ModuleState::FAILED:      return "FAILED";
    case ModuleState::ROLLED_BACK: return "ROLLED_BACK";
    case ModuleState::QUARANTINED: return "QUARANTINED";
  }
  return "UNKNOWN";
}

}  // namespace mm
}  // namespace loracanary
