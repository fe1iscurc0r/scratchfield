// 休眠遥测节点 · epoch 版本化核心主机单元测试（BRAVO B-01）。
//
// 纯逻辑用例（≥6）：epoch 递增 / 不连续触发重同步 / 连续断点恢复 / 时隙分配幂等 /
// 唤醒后 dcp 帧构造 / 深睡配置正确。epoch.cpp 与 wake_sync.cpp 的纯逻辑无 Arduino
// 依赖，lowpower.cpp 走主机桩；dcp 编解码复用 dcp_lora/dcp_frame.cpp（PAPA 线）。
//
// 构建 & 运行（任意装 g++ 的机器）：
//   g++ -std=c++17 -Wall -Wextra -O2 \
//       -I firmware/sleep_epoch -I firmware/dcp_lora \
//       firmware/tests/test_sleep_epoch.cpp \
//       firmware/sleep_epoch/epoch.cpp \
//       firmware/sleep_epoch/wake_sync.cpp \
//       firmware/sleep_epoch/lowpower.cpp \
//       firmware/dcp_lora/dcp_frame.cpp \
//       -o /tmp/test_sleep_epoch && /tmp/test_sleep_epoch
#include <cstdio>
#include <cstring>

#include "epoch.h"
#include "lowpower.h"
#include "wake_sync.h"
#include "dcp_frame.h"

using sleep_epoch::EpochState;
using sleep_epoch::JoinResult;

static int g_checks = 0;
static int g_failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        ++g_checks;                                                          \
        if (!(cond)) {                                                       \
            ++g_failures;                                                    \
            std::fprintf(stderr, "FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); \
        }                                                                    \
    } while (0)

// ---------------------------------------------------------------------------
// 1. epoch 递增
// ---------------------------------------------------------------------------
static void test_epoch_increment() {
    EpochState s;
    s.node_id = 0xABCD;
    CHECK(s.epoch_counter == 0);
    CHECK(!s.initialized);
    CHECK(sleep_epoch::epoch_increment(&s) == 1);
    CHECK(sleep_epoch::epoch_increment(&s) == 2);
    CHECK(s.initialized);
    CHECK(s.epoch_counter == 2);
}

// ---------------------------------------------------------------------------
// 2. epoch 不连续触发重同步
// ---------------------------------------------------------------------------
static void test_epoch_discontinuous_triggers_resync() {
    EpochState s;
    s.node_id = 1;
    s.epoch_counter = 5;
    s.initialized = true;
    s.slot_map[2] = true;   // 旧时隙占用
    s.slot = 2;
    s.slot_owned = true;

    CHECK(!sleep_epoch::is_epoch_contiguous(5, 8));  // gap = 3 > 1
    CHECK(!sleep_epoch::is_epoch_contiguous(5, 4));  // 回退

    JoinResult r = sleep_epoch::epoch_checkpoint_resume(&s, 8);
    CHECK(r == JoinResult::RESYNC);
    // 重同步后 slot_map 清空、本节点不再持有时隙
    CHECK(!sleep_epoch::slot_is_assigned(&s, 2));
    CHECK(!s.slot_owned);
    CHECK(s.epoch_counter == 8);
}

// ---------------------------------------------------------------------------
// 3. epoch 连续断点恢复
// ---------------------------------------------------------------------------
static void test_epoch_contiguous_resume() {
    EpochState s;
    s.node_id = 1;
    s.epoch_counter = 7;
    s.initialized = true;
    s.slot_map[3] = true;
    s.slot = 3;
    s.slot_owned = true;

    CHECK(sleep_epoch::is_epoch_contiguous(7, 8));  // gap = 1
    CHECK(sleep_epoch::is_epoch_contiguous(7, 7));  // gap = 0（同 epoch 重读）

    JoinResult r = sleep_epoch::epoch_checkpoint_resume(&s, 8);
    CHECK(r == JoinResult::FAST_RESUME);
    // 断点恢复：slot_map 保留、本节点时隙不变
    CHECK(sleep_epoch::slot_is_assigned(&s, 3));
    CHECK(s.slot_owned);
    CHECK(s.slot == 3);
    CHECK(s.epoch_counter == 8);
}

// ---------------------------------------------------------------------------
// 4. 时隙分配幂等
// ---------------------------------------------------------------------------
static void test_slot_assign_idempotent() {
    EpochState s;
    s.node_id = 1;
    uint8_t slot = 0;

    CHECK(sleep_epoch::slot_assign(&s, &slot) && slot == 0);   // 首次 → 最小空位 0
    CHECK(sleep_epoch::slot_assign(&s, &slot) && slot == 0);   // 幂等 → 仍 0
    CHECK(s.slot_owned && s.slot == 0);

    // 释放后重新分配：仍应回到 0（最小空位）
    sleep_epoch::slot_release(&s);
    CHECK(!s.slot_owned);
    CHECK(!sleep_epoch::slot_is_assigned(&s, 0));
    CHECK(sleep_epoch::slot_assign(&s, &slot) && slot == 0);

    // 满表：占满 32 个槽后分配失败
    EpochState full;
    for (uint8_t i = 0; i < 32; ++i) full.slot_map[i] = true;
    uint8_t out = 0xFF;
    CHECK(!sleep_epoch::slot_assign(&full, &out));
}

// ---------------------------------------------------------------------------
// 5. 唤醒后 dcp 帧构造（epoch 帧 + REPORT 帧，复用 PAPA 编解码）
// ---------------------------------------------------------------------------
static void test_wake_build_frames() {
    EpochState s;
    s.node_id = 0x1234;
    s.epoch_counter = 42;
    s.slot = 5;
    s.slot_owned = true;
    s.slot_map[5] = true;

    // 5a. epoch 帧：payload 往返 + dcp 帧头/type/CRC 正确（type=0x05 不走 dcp_decode）
    uint8_t frame[DCP_MAX_FRAME];
    size_t n = sleep_epoch::wake_build_epoch_frame(&s, 42, /*resync*/true, 9, frame);
    CHECK(n == 7 + 8);
    CHECK(frame[0] == DCP_MAGIC_0 && frame[1] == DCP_MAGIC_1);
    CHECK(frame[2] == sleep_epoch::DCP_EPOCH);
    // 帧内 CRC 覆盖 type+seq+payload（frame[2 .. n-3)）
    uint16_t crc = dcp_crc16_modbus(frame + 2, 3 + 8);
    CHECK(frame[n - 2] == (uint8_t)(crc & 0xFF));
    CHECK(frame[n - 1] == (uint8_t)((crc >> 8) & 0xFF));

    // epoch payload 解析往返
    uint32_t epoch = 0;
    uint16_t node_id = 0;
    uint8_t slot = 0, flags = 0;
    CHECK(sleep_epoch::epoch_parse_payload(frame + DCP_HEADER_LEN, 8,
                                           &epoch, &node_id, &slot, &flags) == 1);
    CHECK(epoch == 42 && node_id == 0x1234 && slot == 5);
    CHECK((flags & sleep_epoch::EPOCH_FLAG_RESYNC) != 0);

    // 5b. REPORT 帧：走 dcp_decode 往返（现有上报路径兼容）
    uint8_t rf[DCP_MAX_FRAME];
    size_t rn = sleep_epoch::wake_build_report_frame(21.5f, 55, DCP_BATTERY_OK, -85,
                                                     'C', DCP_PROTO_ACURITE_TOWER,
                                                     4660, 3, rf);
    uint8_t rtype = 0, rpayload[9];
    uint16_t rseq = 0;
    int plen = dcp_decode(rf, rn, &rtype, &rseq, rpayload);
    CHECK(plen == 9);
    CHECK(rtype == DCP_REPORT);
    CHECK(rseq == 3);
    dcp_report_t rep;
    CHECK(dcp_parse_report_payload(rpayload, 9, &rep) == 1);
    CHECK(rep.temperature_c == 21.5f && rep.device_id == 4660);
}

// ---------------------------------------------------------------------------
// 6. 深睡配置正确
// ---------------------------------------------------------------------------
static void test_lowpower_validate() {
    char reason[64] = {0};

    // 合理配置：定时 + GPIO 双唤醒源
    sleep_epoch::LowPowerConfig ok = {60, true, true, 8, true};
    CHECK(sleep_epoch::lowpower_validate(ok, reason, sizeof(reason)));

    // 无唤醒源 → 非法
    sleep_epoch::LowPowerConfig none = {0, false, false, 0, true};
    CHECK(!sleep_epoch::lowpower_validate(none, reason, sizeof(reason)));
    CHECK(std::strstr(reason, "wake source") != nullptr);

    // GPIO 引脚越界 → 非法
    sleep_epoch::LowPowerConfig badpin = {60, false, true, 200, true};
    CHECK(!sleep_epoch::lowpower_validate(badpin, reason, sizeof(reason)));
}

int main() {
    test_epoch_increment();
    test_epoch_discontinuous_triggers_resync();
    test_epoch_contiguous_resume();
    test_slot_assign_idempotent();
    test_wake_build_frames();
    test_lowpower_validate();

    if (g_failures == 0) {
        std::printf("🎉 休眠 epoch 核心主机测试通过：%d 断言全部通过\n", g_checks);
        return 0;
    }
    std::fprintf(stderr, "❌ %d/%d 断言失败\n", g_failures, g_checks);
    return 1;
}
