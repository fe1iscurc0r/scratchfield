# dcp-LoRa 帧方案（rf_brain Phase5 · P 线）

> 参考 dcp arXiv 2605.26159（MIT）独立实现，不复制源码。
> 定位：把 ESP32→云服的哨兵上报从「MQTT over TCP」换成「dcp 二进制帧 over LoRa」。
> 帧格式两份实现（Python + C）逐字节兼容，共享本文档作为唯一格式契约。

---

## 一、帧格式表

总长 = 7 + N（N = payload 字节数），硬约束 **最大帧长 < 50B**（N ≤ 42）。

| 偏移 | 字段 | 字节 | 编码 |
|------|------|------|------|
| 0 | magic | 2 | `0xD0 0xCC`（同步字，与 MeshRadio `0x4D 0x52` 无交集） |
| 2 | type | 1 | 消息类型枚举 |
| 3 | seq | 2 | uint16 **小端** |
| 5 | payload | N | 载荷（按 type 定长/变长） |
| 5+N | crc | 2 | CRC-16 MODBUS **小端** |

**消息类型 type**：

| 值 | 类型 | payload 长度 |
|----|------|-------------|
| 0x01 | REPORT（上报） | 9B 定长 |
| 0x02 | COMMAND（命令） | 变长（≤42B，上层自声明） |
| 0x03 | ACK | 0B |
| 0x04 | HEARTBEAT | 0B |

**REPORT payload（9B，对齐 sentinel_bridge NDJSON 七字段）**：

| 偏移 | 字段 | 类型 | 编码 | 例 |
|------|------|------|------|-----|
| 0 | temperature_c | int16 LE | ×10 | 25.0 → `FA 00` |
| 2 | humidity_pct | uint8 | 原值 | 50 → `32` |
| 3 | battery | uint8 | 0=OK 1=LOW | OK → `00` |
| 4 | rssi_dbm | int8 | round | -85 → `AB` |
| 5 | channel | uint8 | ASCII 码 | "C" → `43` |
| 6 | protocol | uint8 | 枚举 | acurite-tower → `00` |
| 7 | device_id | uint16 LE | 原值 | 4660 → `34 12` |

**枚举表**：

```
protocol: 0=acurite-tower  1=acurite-515  2=lacrosse-tx141th-bv2
          3=acurite-5n1    4=acurite-atlas  255=unknown
battery:  0=OK  1=LOW
```

**CRC-16 MODBUS**：poly `0x8005`（反射 `0xA001`）、init `0xFFFF`、refin/refout true，
覆盖 `type + seq + payload`（不含 magic）。标准向量 `b"123456789"` → `0x4B37`。

**典型帧长**：REPORT 16B、ACK/HEARTBEAT 7B、COMMAND ≤49B。REPORT 主帧 16B 对
LoRa 单包 255B（实际可用 ~200B）无压力，比 MQTT 省一个数量级。

---

## 二、MQTT → dcp 对比

| 维度 | MQTT over TCP | dcp over LoRa |
|------|---------------|---------------|
| 单条上报开销 | ≥100B（CONNECT 握手 + topic 名 + JSON 字段名 + PUBLISH 头） | **16B**（定长二进制） |
| 传输层 | TCP（三次握手 + 保活） | LoRa 直接空中帧，无连接 |
| 功耗/带宽 | 高（TCP 长连） | 低（按需发帧） |
| 可靠性 | QoS 0/1/2（broker 侧） | seq + CRC-16 + ACK 重传（应用层） |
| 时延 | 中（broker 中转） | 低（点对点） |
| 依赖 | broker（Mosquitto 等） | 无（SX1278 直连） |
| 载荷可读性 | JSON 文本 | 二进制（需解码） |

**取舍**：dcp 牺牲了 JSON 可读性与 broker 生态，换来了 LoRa 窄带下的低开销、
无 broker 依赖。REPORT 是主帧，字段定长无变长歧义。

---

## 三、真机联调清单（≥5 步，用户按序实测）

1. **烧录**：`cd firmware && pio run -t upload`（ESP32-S3 + SX1278，接线照 `firmware/README.md`）。
2. **上电自检**：串口（115200）出 `{"src":"sentinel","ready":true}`，无 `error`。
3. **发 STATUS**：串口发 `STATUS`，返回固件频率/带宽/扩频因子配置。
4. **发 REPORT 帧**：触发传感器（或手动调用 `dcp_lora_send(DCP_REPORT, ...)`），
   节点空中发出 16B dcp 帧。
5. **收帧校验 CRC**：对端（另一节点或云服 SDR）收到帧，`dcp_crc16_modbus` 校验通过；
   可先跑 `dcp_frame_selftest()`（C 侧自测，含标准向量 `0x4B37`）确认 CRC 实现正确。
6. **云服解帧入库**：云服侧用 `mcpserver/rf_brain/dcp/frame.py` 的 `decode` + `parse_report_payload`
   解出温度/湿度/RSSI/电压，喂入 `sentinel_bridge.ingest` 入库。

---

## 四、已知限制（诚实标注）

- **C 侧未编译验证**：云服无 ESP32 工具链，`firmware/dcp_lora/` 未经 `pio run` 编译。
  RadioLib API（SX1278 `begin` 签名 / `transmit` / `readData`）若与实际版本有差异，
  按编译错误微调。
- **LoRa 参数待调**：带宽 125kHz / SF7 是保守起点，真机距离/误码率不达标时调 SF（7→12）。
- **COMMAND 语义未定义**：变长命令的 payload 结构由上层命令层自声明，dcp 只提供帧编解码。
- **与 mesh_layer 正交**：dcp 无加密/路由/TTL，只做「字节 ↔ 结构化载荷 + CRC 完整性」；
  需要多跳组网时由 mesh_layer 承载 dcp 帧，本单不重复实现。
