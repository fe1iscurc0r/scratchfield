// 休眠遥测节点 · 唤醒 + epoch 快速入网序列实现（BRAVO B-01）。
//
// 帧构造复用 firmware/dcp_lora/dcp_frame.{h,cpp}（PAPA 线产物），与
// mcpserver/rf_brain/dcp/frame.py 逐字节兼容。
#include "wake_sync.h"

#include "dcp_frame.h"

namespace sleep_epoch {

JoinResult wake_fast_join(EpochState* s, uint32_t current_epoch) {
    return epoch_checkpoint_resume(s, current_epoch);
}

size_t wake_build_epoch_frame(const EpochState* s, uint32_t epoch,
                              bool resync_requested, uint16_t seq, uint8_t* out) {
    uint8_t payload[EPOCH_PAYLOAD_LEN];
    if (epoch_build_payload(s, epoch, resync_requested, payload) == 0) {
        return 0;
    }
    return dcp_encode(DCP_EPOCH, seq, payload, EPOCH_PAYLOAD_LEN, out);
}

size_t wake_build_report_frame(float temperature_c, uint8_t humidity_pct,
                               uint8_t battery, int8_t rssi_dbm,
                               uint8_t channel, uint8_t protocol,
                               uint16_t device_id, uint16_t seq, uint8_t* out) {
    uint8_t payload[DCP_REPORT_PAYLOAD_LEN];
    if (dcp_build_report_payload(temperature_c, humidity_pct, battery, rssi_dbm,
                                 channel, protocol, device_id, payload) == 0) {
        return 0;
    }
    return dcp_encode(DCP_REPORT, seq, payload, DCP_REPORT_PAYLOAD_LEN, out);
}

}  // namespace sleep_epoch
