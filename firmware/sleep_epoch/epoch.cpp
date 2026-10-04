// 休眠遥测节点 · epoch 版本化核心实现（纯 C++，无 Arduino 依赖，可主机编译）。
//
// 逻辑与 mcpserver/rf_brain/sleep_sync.py 的 epoch 字段逐字节对齐；
// 持久化（RTC backup / NVS）由 lowpower.cpp 注入，本层只做纯逻辑。
#include "epoch.h"

namespace sleep_epoch {

uint32_t epoch_increment(EpochState* s) {
    if (s == nullptr) {
        return 0;
    }
    ++s->epoch_counter;
    s->initialized = true;
    return s->epoch_counter;
}

bool is_epoch_contiguous(uint32_t last, uint32_t current) {
    // 连续：current == last（同 epoch 重读）或 current == last + 1（正常步进）。
    // 回退（current < last）或 gap > 1 视为不连续。
    if (current < last) {
        return false;
    }
    return (current - last) <= 1;
}

JoinResult epoch_checkpoint_resume(EpochState* s, uint32_t current) {
    if (s == nullptr) {
        return JoinResult::RESYNC;
    }
    if (s->initialized && is_epoch_contiguous(s->epoch_counter, current)) {
        // 连续：保留 slot_map，从断点恢复
        s->epoch_counter = current;
        return JoinResult::FAST_RESUME;
    }
    // 不连续（或首次）：清 slot_map，触发重同步
    s->epoch_counter = current;
    s->initialized = true;
    slot_release(s);
    for (size_t i = 0; i < SLOT_MAP_MAX; ++i) {
        s->slot_map[i] = false;
    }
    return JoinResult::RESYNC;
}

bool slot_assign(EpochState* s, uint8_t* out_slot) {
    if (s == nullptr || out_slot == nullptr) {
        return false;
    }
    // 幂等：本节点已持有且该时隙仍被占用 → 原样返回
    if (s->slot_owned && s->slot < SLOT_MAP_MAX && s->slot_map[s->slot]) {
        *out_slot = s->slot;
        return true;
    }
    // 找最小空位
    for (uint8_t i = 0; i < SLOT_MAP_MAX; ++i) {
        if (!s->slot_map[i]) {
            s->slot_map[i] = true;
            s->slot = i;
            s->slot_owned = true;
            *out_slot = i;
            return true;
        }
    }
    return false;  // 时隙全满
}

void slot_release(EpochState* s) {
    if (s == nullptr) {
        return;
    }
    if (s->slot_owned && s->slot < SLOT_MAP_MAX) {
        s->slot_map[s->slot] = false;
    }
    s->slot_owned = false;
    s->slot = 0;
}

bool slot_is_assigned(const EpochState* s, uint8_t slot) {
    if (s == nullptr || slot >= SLOT_MAP_MAX) {
        return false;
    }
    return s->slot_map[slot];
}

size_t epoch_build_payload(const EpochState* s, uint32_t epoch,
                           bool resync_requested, uint8_t* out) {
    if (out == nullptr) {
        return 0;
    }
    uint16_t node_id = (s != nullptr) ? s->node_id : 0;
    uint8_t  slot    = (s != nullptr) ? s->slot : 0;

    out[0] = (uint8_t)(node_id & 0xFF);
    out[1] = (uint8_t)((node_id >> 8) & 0xFF);
    out[2] = (uint8_t)(epoch & 0xFF);
    out[3] = (uint8_t)((epoch >> 8) & 0xFF);
    out[4] = (uint8_t)((epoch >> 16) & 0xFF);
    out[5] = (uint8_t)((epoch >> 24) & 0xFF);
    out[6] = slot;
    out[7] = resync_requested ? EPOCH_FLAG_RESYNC : 0;
    return EPOCH_PAYLOAD_LEN;
}

int epoch_parse_payload(const uint8_t* payload, size_t len,
                        uint32_t* epoch, uint16_t* node_id,
                        uint8_t* slot, uint8_t* flags) {
    if (payload == nullptr || len != EPOCH_PAYLOAD_LEN) {
        return 0;
    }
    if (node_id != nullptr) {
        *node_id = (uint16_t)(payload[0] | (payload[1] << 8));
    }
    if (epoch != nullptr) {
        *epoch = (uint32_t)(payload[2] | (payload[3] << 8) |
                            (payload[4] << 16) | (payload[5] << 24));
    }
    if (slot != nullptr) {
        *slot = payload[6];
    }
    if (flags != nullptr) {
        *flags = payload[7];
    }
    return 1;
}

}  // namespace sleep_epoch
