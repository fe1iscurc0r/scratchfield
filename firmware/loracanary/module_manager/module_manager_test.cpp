/* LoRaCanary · 模块管理器自测（主机 g++ 可编译运行，无 Arduino 依赖）。
 *
 * 构建：g++ -std=c++17 module_manager.cpp module_manager_test.cpp -o mm_test && ./mm_test
 * 覆盖：
 *   - 健康模块连续自检合格 → 不回滚；
 *   - 失效模块（RSSI 越界）连续失败达阈值 → 自动回滚到 prev 槽位，状态推进正确；
 *   - 单版本（无 prev）不回滚 → 置 FAILED；
 *   - 回滚后仍连续失败 → 隔离（QUARANTINED），停止再回滚；
 *   - 重复注册不覆盖运行期状态。
 */
#include "module_manager.h"

#include <cassert>
#include <cstdio>

using namespace loracanary::mm;

// 自检回调：RSSI 低于 -110dBm 判失效（模拟 SX1278 断链 / 天线脱落）。
static int rf_self_check(const HardwareFeedback &fb) {
  int score = 100;
  if (!fb.power_ok) score -= 40;
  if (!fb.spi_ok) score -= 30;
  if (fb.rssi_dbm < -110) score -= 40;  // 断链 → 60 分 → 但其它项再扣会低于阈值
  return score;
}

// 自检回调：只看 I2C 应答，用于「健康模块不回滚」对照。
static int bme_self_check(const HardwareFeedback &fb) {
  return fb.i2c_ok ? 90 : 10;
}

int main() {
  // ---- 场景 1：失效模块连续失败 → 自动回滚 ----
  {
    ModuleManager mgr;
    ModuleDescriptor rf;
    rf.id = "rf";
    rf.active = ModuleVersion{1, 5, 0};  // 当前 A 槽位 v1.5
    rf.prev = ModuleVersion{1, 4, 1};    // 上一良好 B 槽位 v1.4
    rf.self_check = rf_self_check;
    rf.fail_threshold = 3;
    mgr.register_module(rf);

    HardwareFeedback bad;                 // 断链：power/spi 坏 + RSSI 极低
    bad.power_ok = false;
    bad.spi_ok = false;
    bad.rssi_dbm = -120;

    // 前两次失败未达阈值，第三次达阈值触发回滚
    for (int i = 0; i < 2; ++i) {
      mgr.run_health_check(bad);
      assert(mgr.evaluate_and_rollback().rolled.empty());  // 未达阈值，不回滚
    }
    mgr.run_health_check(bad);                          // 第 3 次连续失败
    auto rolled = mgr.evaluate_and_rollback().rolled;   // 达阈值 → 回滚
    assert(rolled.size() == 1 && rolled[0] == "rf");

    const ModuleDescriptor *m = mgr.find("rf");
    assert(m->state == ModuleState::ROLLED_BACK);
    assert(m->active == (ModuleVersion{1, 4, 1}));  // 切到上一版本
    assert(m->prev == (ModuleVersion{1, 5, 0}));    // 旧激活留档
    assert(m->consecutive_fails == 0);              // 回滚后清零
    assert(m->epoch == 1);                          // 生命周期 +1
    std::printf("[PASS] 场景1：失效模块连续失败→自动回滚（v1.5→v1.4）\n");
  }

  // ---- 场景 2：健康模块不回滚，一次合格清零连续失败 ----
  {
    ModuleManager mgr;
    ModuleDescriptor bme;
    bme.id = "bme";
    bme.active = ModuleVersion{2, 0, 0};
    bme.prev = ModuleVersion{1, 9, 1};
    bme.self_check = bme_self_check;
    bme.fail_threshold = 3;
    mgr.register_module(bme);

    HardwareFeedback ok;        // 全健康
    HardwareFeedback bad_i2c;   // I2C 坏
    bad_i2c.i2c_ok = false;

    mgr.run_health_check(bad_i2c);   // fail 1
    mgr.run_health_check(bad_i2c);   // fail 2
    mgr.run_health_check(ok);        // 一次合格 → 清零
    mgr.run_health_check(bad_i2c);   // fail 1（重新计）
    mgr.run_health_check(bad_i2c);   // fail 2（仍未达 3）

    auto rolled = mgr.evaluate_and_rollback();
    assert(rolled.rolled.empty() && rolled.quarantined.empty());
    const ModuleDescriptor *m = mgr.find("bme");
    assert(m->state == ModuleState::ACTIVE);
    assert(m->consecutive_fails == 2);  // 滞回：合格后重新累计到 2
    std::printf("[PASS] 场景2：健康模块不回滚，合格清零连续失败\n");
  }

  // ---- 场景 3：单版本（无 prev）不回滚 → 置 FAILED ----
  {
    ModuleManager mgr;
    ModuleDescriptor rf;
    rf.id = "rf";
    rf.active = ModuleVersion{1, 5, 0};
    rf.prev = rf.active;        // 无上一版本可回滚
    rf.self_check = rf_self_check;
    rf.fail_threshold = 2;
    mgr.register_module(rf);

    HardwareFeedback bad;
    bad.power_ok = false;
    bad.spi_ok = false;
    bad.rssi_dbm = -120;

    mgr.run_health_check(bad);
    mgr.run_health_check(bad);
    auto rolled = mgr.evaluate_and_rollback();
    assert(rolled.rolled.empty());                  // 无回滚目标
    assert(mgr.find("rf")->state == ModuleState::FAILED);
    std::printf("[PASS] 场景3：单版本无 prev 不回滚，置 FAILED\n");
  }

  // ---- 场景 5：回滚后仍连续失败 → 隔离（QUARANTINED）----
  {
    ModuleManager mgr;
    ModuleDescriptor rf;
    rf.id = "rf";
    rf.active = ModuleVersion{1, 5, 0};
    rf.prev = ModuleVersion{1, 4, 1};
    rf.self_check = rf_self_check;
    rf.fail_threshold = 2;
    mgr.register_module(rf);

    HardwareFeedback bad;
    bad.power_ok = false;
    bad.spi_ok = false;
    bad.rssi_dbm = -120;

    // 第一次连续失败 → 回滚到 v1.4
    mgr.run_health_check(bad);
    mgr.run_health_check(bad);
    auto first = mgr.evaluate_and_rollback();
    assert(first.rolled.size() == 1 && first.rolled[0] == "rf");
    assert(mgr.find("rf")->state == ModuleState::ROLLED_BACK);

    // 回滚后（v1.4）仍连续失败 → 隔离，不再回滚
    mgr.run_health_check(bad);
    mgr.run_health_check(bad);
    auto second = mgr.evaluate_and_rollback();
    assert(second.rolled.empty());
    assert(second.quarantined.size() == 1 && second.quarantined[0] == "rf");
    assert(mgr.find("rf")->state == ModuleState::QUARANTINED);

    // 隔离后不再体检：健康反馈也不会恢复状态
    HardwareFeedback ok;
    mgr.run_health_check(ok);
    assert(mgr.find("rf")->state == ModuleState::QUARANTINED);
    std::printf("[PASS] 场景5：回滚后仍失败→隔离，隔离后停止体检\n");
  }

  // ---- 场景 4：重复注册不覆盖运行期状态 ----
  {
    ModuleManager mgr;
    ModuleDescriptor rf;
    rf.id = "rf";
    rf.active = ModuleVersion{1, 5, 0};
    rf.prev = ModuleVersion{1, 4, 1};
    rf.self_check = rf_self_check;
    rf.fail_threshold = 1;
    mgr.register_module(rf);

    HardwareFeedback bad;
    bad.power_ok = false;
    bad.spi_ok = false;
    bad.rssi_dbm = -120;
    mgr.run_health_check(bad);
    mgr.evaluate_and_rollback();
    assert(mgr.find("rf")->state == ModuleState::ROLLED_BACK);

    ModuleDescriptor dup;        // 同 id 再注册
    dup.id = "rf";
    dup.active = ModuleVersion{9, 9, 0};
    dup.prev = ModuleVersion{9, 8, 1};
    dup.self_check = rf_self_check;
    mgr.register_module(dup);    // 应被忽略
    assert(mgr.find("rf")->active == (ModuleVersion{1, 4, 1}));  // 状态未被覆盖
    std::printf("[PASS] 场景4：重复注册不覆盖运行期状态\n");
  }

  std::printf("ALL PASS\n");
  return 0;
}
