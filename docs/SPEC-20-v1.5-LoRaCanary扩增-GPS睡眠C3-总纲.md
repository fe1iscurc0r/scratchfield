# SPEC-20 · LoRa 环境感知节点（LoRaCanary）· 总纲 · v1.5 扩增（GPS + 深度睡眠 + C3 轻量节点）

> 状态：施工中（2026-08-29 AB 线立项——在 v1（AA 线）基础上加 GPS 定位上报 + 深度睡眠 + ESP32-C3 轻量节点）
> 读者：AB 智能体（固件施工）/ 实验田维护者（评审）/ 用户（PCB + 真机验证）
> 基线：[SPEC-20-LoRa环境感知节点-总纲.md](SPEC-20-LoRa环境感知节点-总纲.md)（v1 契约全部保留：帧头 0xD0CC、CRC-16 MODBUS、≤120B 载荷、二进制帧纪律）
> 工单：AB-01 帧协议扩展 / AB-02 C3 节点固件 / AB-03 深度睡眠 / AB-04 网关兼容 + 测试 + 文档

---

## 〇、一句话定位

**v1.5 = v1 + 定位 + 省电 + 轻量节点：C3 节点每 60s 深睡唤醒一次，GPS（NEO-6M）拿定位 + BME280 拿温湿压，组 GEO 帧经 433MHz LoRa 发给网关；无定位时 sat=0 诚实降级照发，不丢帧。**

## 一、边界（P3）

| 做（v1.5 纳入） | 不做（显式排除） |
|---|---|
| GEO 帧 type=0x03（t/h/p/lat/lng/alt/sat） | 破坏 v1 已有 ENV(0x01)/HEARTBEAT(0x02)/ACK(0xFE)/ERR(0xFF) 兼容 |
| C3 节点固件：NEO-6M GPS + BME280 + SX1278 + 周期上报 | 多跳 mesh / 加密 / 新传感器 |
| 深度睡眠：Timer 唤醒默认 60s，RTC 保持 node_id/seq/epoch | GPS 冷启动 TTFF 优化（热启动策略即可，真机再调） |
| S3 网关 GEO 解析 → 上行 JSON 加 lat/lng/alt/sat/gps_fix | MCU 侧 MQTT/JSON（LoRa 链路只走二进制帧，铁律不变） |
| 降级路径：无 GPS fix 照发 sat=0；无 BME280 用 MOCK 标注 | 功率超配（仍 433MHz ≤100mW，铁律不变） |

## 二、GEO 帧格式（type=0x03，逐字段契约）

帧结构沿用 v1：`[0xD0 0xCC] [type:1] [seq:1] [node_id:1] [payload:N] [crc16:2 LE]`，CRC 覆盖 type+seq+node_id+payload。

GEO payload 逐字段（Python `struct` 顺序，Python/C++ 逐字节一致）：

| 顺序 | 字段 | 类型 | 缩放 | 说明 |
|---|---|---|---|---|
| 1 | t | int16 LE | ×100 | 温度 ℃，26.3℃ → 2630 |
| 2 | h | uint8 | 1 | 湿度 %（1% 分辨率，同 v1 ENV 勘误） |
| 3 | p | uint32 LE | ×100 | 气压 hPa，1013.2 → 101320 |
| 4 | lat | int32 LE | ×1e7 | 纬度，39.9042 → 399042000（±180° 均在 int32 内） |
| 5 | lng | int32 LE | ×1e7 | 经度，116.4074 → 1164074000 |
| 6 | alt | int16 LE | 1 | 海拔 m（有符号） |
| 7 | sat | uint8 | 1 | 卫星数，0 = 无定位 |

**载荷长度勘误（诚实标注）**：上表 7 字段合计 2+1+4+4+4+2+1 = **18B，总帧 25B**；立项工单写的「payload 定长 16B / 总帧 23B」为算术笔误——按字段清单逐字节实现才是唯一自洽读法（16B 会丢字段、破坏编解码往返）。仍是定长结构，仍远小于 120B 上限，铁律不破。

**降级规则**：sat=0 时 encode 强制 lat/lng/alt=0（无定位不报假坐标）；decode 对任意输入不崩，坏帧返回 None。

## 三、C3 节点引脚（合宙 ESP32-C3 插接模块）

| 外设 | 引脚 | 备注 |
|---|---|---|
| NEO-6M GPS | UART1 RX ← GPS TX（9600 8N1） | 四接口插接件 VCC/GND/TX/RX；RX 可不接（只收不发） |
| BME280 | I2C：IO4=SDA IO5=SCL | 地址自动探测 0x76/0x77 |
| SX1278 | SPI：IO6=MOSI IO7=MISO IO8=SCK IO9=CS IO10=DIO0 IO11=RST | 433MHz SF7/BW125/CR4/5，照 v1 RadioLib 参数 |
| 外设电源控制 | 代码留接口（MOS 管方案，GPIO 拉低断电） | 真机接 MOS 栅极后填引脚号 |
| 深度睡眠 | esp_sleep_enable_timer_wakeup(SLEEP_INTERVAL_S×1e6) | SLEEP_INTERVAL_S 默认 60，真机实测后可调 300 |

## 四、深度睡眠策略（AB-03）

1. 唤醒 → 外设上电 → GPS 热启动等 fix（≤2s 窗）→ BME280 → 组 GEO 帧 → LoRa 发送 → 外设断电 → 回睡
2. `RTC_DATA_ATTR` 保持 node_id / seq / epoch 跨唤醒（seq 不回卷；掉电冷启动归零是预期行为）
3. 无 fix → sat=0 降级照发；SLEEP_INTERVAL_S 可配置，注释写明真机实测后可调 300s
4. SX1278 用 RST 软复位兜底；GPS TTFF 真机实测后记录进 README

## 五、测试用例（AB-04，≥16 passed）

v1 十二例（SPEC-20 第七节原样保留）+ v1.5 新增：
13. GEO 编解码往返（t/h/p/lat/lng/alt/sat 全字段）
14. GEO 无定位降级（sat=0 → lat/lng/alt=0，decode 不崩）
15. GEO 超长/坏帧拒绝（payload ≠18B、CRC 错、magic 错 → None）
16. 睡眠状态保持（Python 镜像 RTC 计数：跨唤醒 seq 连续、冷启动归零）

## 六、验收标准（可执行不变量）

```bash
cd tools && pytest -q                                      # ≥16 passed
python -c "from lora_frame import encode,decode; b=encode(geo=True,t=26.3,h=55,p=1013.2,lat=39.9042,lng=116.4074,alt=52,sat=8); d=decode(b); assert abs(d['lat']-39.9042)<1e-6 and abs(d['lng']-116.4074)<1e-6; print('OK')"
grep -n "esp_sleep_enable_timer_wakeup\|esp_deep_sleep_start" firmware/loracanary/c3_node/*  # 非空
grep -rn "requests.post\|openai\|anthropic" firmware/loracanary tools/lora_frame.py          # 空（无 LLM 调用）
```

**真机验证点（用户实测，样例数据诚实标注）**：C3+GPS 对打（网关收到含 lat/lng/sat 的 JSON）/ 深度睡眠电流实测（USB 电流表，目标 <100µA 级）/ GPS 冷启动 TTFF 统计（决定周期 60s→300s）/ PCB 底板加 C3 排母。

## 七、提交规范

- 分项 commit：`feat(loracanary): AB-0x ...`（各单一个）+ `docs(loracanary): ...`
- 成果推 `trae/agent-ab` 分支（新线，不污染 AA 已收口产物）
- 中文注释/输出；阻塞不硬做，写清原因
