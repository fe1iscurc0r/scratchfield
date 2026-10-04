# iotgateway 协议边缘终结 授粉报告（卷102 W102-03 · P0）

- 日期：2026-09-11
- 源：https://github.com/yjiong/iotgateway（191★，MIT，Go）
- 目标：`tools/protocol_gateway_probe.py`（协议→统一 MQTT 语义转换最小骨架）
- 施工分支：trae/agent-102

## 一、源→目标映射

| 源（yjiong/iotgateway） | 目标（本仓库） | 映射关系 |
|---|---|---|
| `internal/device/device.go:48 Devicer` 接口 + `:59 Device` 基础结构 | `protocol_gateway_probe.DeviceAdapter` | 协议设备适配抽象对应 |
| `internal/device/ammeter/pmc340.go:19 PMC340`（具体电表协议） | `DeviceAdapter(protocol="modbus-rtu", fields=...)` | 具体协议设备的实例化路径对应 |
| `internal/handler/mqtt_handler.go:139` topic 拼接（ServerID/ClientID 层级）+ data-up 发布 | `ProtocolGateway.topic_for`（`gateway/{id}/data` 规范） | 统一总线出口语义对应 |
| 协议接入→转换→发布三层 | `register + map_to_payload + read_and_publish` | 分层职责复刻（无 broker 依赖） |

## 二、核心数据结构共鸣（附源行号）

1. **适配接口与设备实体分离**：源把「协议读取做什么」抽成 `Devicer` 接口（`device.go:48`），设备基础信息放 `Device` 结构（`:59`）；本探针同样把协议字段/换算抽到 `DeviceAdapter` 数据类，网关只做「读取→映射→发布」的通用流程。
2. **字段级换算表驱动**：源的具体设备（如 PMC340）内置寄存器→物理量映射；本探针用 `fields: 字段名 -> (偏移, 缩放系数, 单位)` 三元组表驱动换算，同一个 `map_to_payload` 覆盖任意协议设备。
3. **topic 层级即数据契约**：源在 `mqtt_handler.go:139` 以 `ServerID + "/" + ClientID` 拼接主题并区分 data-up / data-send 方向；本探针将「协议终结层 topic 规范」定为 `gateway/{device_id}/data` 单向数据上报，下行（data-send）留待对接 Hermes 决策层时再加。

## 三、难度 × 收益

- 难度：★★☆（无 broker 依赖的纯数据流模拟，约 90 行 + 3 测试）
- 收益：★★★（遥测总线「协议边缘终结」的第一块积木：任何设备协议在边缘翻译成统一 JSON/MQTT 语义后，台账/决策层不再关心协议细节）

## 四、结论与接入建议（≥3）

1. **topic 规范（草案）**：数据上行 `gateway/{device_id}/data`，下行 `gateway/{device_id}/cmd`，现场/状态 `gateway/{device_id}/meta`——探针已验证上行语义，进台账时按此命名。
2. **适配层即插件**：新协议只加一个 `DeviceAdapter`（字段表），网关零改动——与 sentinel（W102-05）/qbee（W102-02）注册客户端共用「设备 ID 一致」约束。
3. **边缘终结在树莓派/ESP32 网关**：iotgateway 单二进制可部署在边缘；本仓若自建，探针的 `read_and_publish` 直接换成 paho 客户端即可，不引新依赖时先落 JSON 日志出口。
4. **换算表进台账**（呼应 W102-07 schema）：设备能力字段直接存 `fields` 三元组的序列化，让台账具备「协议翻译字典」能力。

## 五、许可裁定

yjiong/iotgateway 为 **MIT**（仓库根 LICENSE），可参考实现；本探针为独立重写（无 broker 依赖的最小语义骨架），未复制源代码。裁定：**安全**。

## 六、验收

`tools/test_protocol_gateway_probe.py`：3 项测试全绿（寄存器读取 / 缩放换算映射 / 多设备 topic 规范发布）。