# LoRa chirp 发射功率估算器（符号时长 / ToA / 能量 / 链路预算 / 频谱占用）

- goal: 设计一个 LoRa chirp 在 433 MHz 的发射功率估算器，给定扩频因子 7，输出功率 14 dBm
- rf_lib: stdlib
- 生成器: mcpserver.rf_workflow.prompt_to_script（模板 lora_chirp_power_estimator）

## 解析出的规格（`spec_sources` 标注每个字段来自 goal / llm / default）

```json
{
 "bw_hz": 125000.0,
 "cable_loss_db": 0.0,
 "channel_spacing_hz": null,
 "cr": 1,
 "crc": 1,
 "freq_hz": 433000000.0,
 "implicit_header": false,
 "kind": "lora_chirp_power_estimator",
 "low_data_rate_optimize": null,
 "payload_bytes": 16,
 "preamble_symbols": 8,
 "rx_antenna_gain_dbi": 0.0,
 "sample_rate_hz": 250000.0,
 "sf": 7,
 "spec_sources": {
  "bw_hz": "default",
  "cr": "default",
  "freq_hz": "goal",
  "payload_bytes": "default",
  "sf": "goal",
  "tx_power_dbm": "goal"
 },
 "spectrum_symbols": 1,
 "target_distance_m": 1000.0,
 "tx_antenna_gain_dbi": 0.0,
 "tx_period_s": 60.0,
 "tx_power_dbm": 14.0
}
```
