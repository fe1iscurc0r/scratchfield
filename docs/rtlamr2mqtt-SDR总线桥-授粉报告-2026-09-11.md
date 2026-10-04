# rtlamr2mqtt SDR 总线桥 授粉报告（卷102 W102-04 · P0）

- 日期：2026-09-11
- 源：https://github.com/allangood/rtlamr2mqtt（621★，MIT；当前主分支为 Home Assistant addon Python 重写版）
- 目标：`tools/sdr_mqtt_probe.py`（SDR/表计读数 → 统一 MQTT 语义的总线桥最小骨架）
- 施工分支：trae/agent-102

## 一、源→目标映射

| 源（rtlamr2mqtt addon） | 目标（本仓库） | 映射关系 |
|---|---|---|
| `app/helpers/read_output.py:43 read_rtlamr_output`（解码输出 → 结构化） | `sdr_mqtt_probe.parse_rtlamr_line` | 读数解析对应 |
| `app/helpers/read_output.py:52 get_message_for_ids`（按表计 ID 过滤分发） | `SdrMqttBridge.publish_meter`（按 meter_id 路由主题） | 分发语义对应 |
| `app/helpers/ha_messages.py:8 meter_discover_payload`（发现/元信息载荷） | `SdrMqttBridge.discover_payload` | 发现载荷对应 |
| `ha_messages.py:19/57/58` attributes/state/status 三级主题 | `attributes_topic/state_topic/availability_topic` | topic 三分法直接借鉴 |

## 二、核心数据结构共鸣（附源行号）

1. **读数即事件**：源把 rtlamr 解码输出整理为结构化读数再分发（`read_output.py:43`）；本探针的 `MeterReading`（meter_id/type/value/unit/ts）是同一语义的最小化，且扩展出 `SpectrumSample`（band/freq_hz/dbm/ts）承载 rf_brain 频谱读数。
2. **topic 三分法**：源以 `{base}/{meter_id}/attributes|state`（`:19/:57`）加 `{base}/status`（`:58`）分离元信息/数值/在线状态；本探针原样采用三分之一法并推广到频谱（`sdr/spectrum/{band}/state`），保证总线语义统一。
3. **发现载荷自引用 topic**：源在 `meter_discover_payload`（`:8`）里写明 state/availability 主题供订阅方自动发现；本探针 `discover_payload` 同构（`disc["state_topic"]` 与 `state_topic()` 一致，测试验证）。

## 三、难度 × 收益

- 难度：★★☆（纯字符串/JSON 语义模拟，无 broker 依赖，约 110 行 + 3 测试）
- 收益：★★★（rf_brain/频谱站读数获得统一总线出口设计——现状数据散落；topic 规范可直接作为遥测总线数据层契约）

## 四、结论与接入建议（≥3）

1. **总线 topic 规范（草案）**：`sdr/meter/{id}/state`（表计数）、`sdr/spectrum/{band}/state`（频段谱读数）、`sdr/status`（桥在线）——后续探头/感知源一律对齐此三分法。
2. **mosquitto 落地方案**：探针的 sink 换成 paho-mqtt 即可接 mosquitto（dns/433 桥同机部署）；不引新依赖阶段先落 JSONL 日志文件。
3. **与 rf_brain 感知层对接**：频谱读数由 `tools/sdr_proc.py` 产出后经 `publish_spectrum` 上总线；每 band 一条 state 主题、低频聚合用 attributes 主题，避免高频刷总线。
4. **解析器容错**：rtlamr 输出行格式漂移是常态——探针的解析 None 回退模式进生产时保留，坏行计数走 `sdr/status` 的健康字段。

## 五、许可裁定

rtlamr2mqtt（allangood）为 **MIT**（仓库根 LICENSE），可参考；本探针为独立实现（未复制源码，topic 分层为常识性命名）。裁定：**安全**。

## 六、验收

`tools/test_sdr_mqtt_probe.py`：3 项测试全绿（读数解析含容错 / topic 三分法+发现载荷自引用 / 表计与频谱两类记录总线化）。