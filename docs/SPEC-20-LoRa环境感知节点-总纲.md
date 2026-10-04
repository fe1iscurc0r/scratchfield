# SPEC-20 · LoRa 环境感知节点（LoRaCanary）· 总纲 · v1

> 状态：待施工（2026-08-26 立项——用户定方向：边缘触点网格 + 嘉立创 AI 绘图试水；难度适中）
> 用途：给 AI 装"多点多感官"——LoRa 节点群采集环境数据（温/湿/压）→ 网关汇聚 → 主机（冥王峡谷/天选7/云服 rf_brain）
> 读者：Trae（固件施工）/ 沈遥（评审）/ 用户（PCB + 真机验证）
> 依据：SPEC-17/18/19 架构裁决（独立组件+总线）；授粉 dcp 帧协议、HW-01 mesh_layer.py（MeshRadio v7 移植）、round5 MCU 通讯；phone-mobile-hub Day6；立创开源 robba「基于LoRa的无线通信装置」（模块划分参考）；用户储备芯片

---

## 〇、一句话定位

**LoRaCanary = 环境感知节点 + 网关：节点（ESP32-S3 SuperMini + SX1278 + BME280 + OLED）每 30s 通过 433MHz LoRa 上报环境数据，网关汇聚后走 USB 串口 / WiFi MQTT 进主机，让 AI 能"感知"多个物理点位。**

## 一、背景与边界（P3 边界）

| 做（v1 纳入） | 不做（显式排除） |
|---|---|
| 节点固件：BME280/BMP280 温湿压采集 + OLED 显示 + 周期上报 | 多跳 mesh（v2——mesh_layer.py 已备好，v1 用星型单跳） |
| LoRa 收发：SX1278 模块，433MHz，SF7/BW125/CR4/5，dcp 风格二进制帧（magic 0xD0CC + type + seq + node_id + payload + CRC16） | 射频芯片级集成（SX1278 焊芯片+阻抗匹配——模块化插接，射频坑留给模块厂） |
| 网关固件：LoRa 接收 → 串口 JSON / WiFi MQTT 双上行 | 手机 APP/前端（主机侧工具后续再说） |
| 模块化底板 PCB（用户用嘉立创 AI 画，SPEC 给约束） | v1 加密（明文案+CRC；AES 留 v2） |
| 测试 ≥12 + 诚实降级 | FT8/SSTV/APT 等解码（Y 工单的事，不混） |
| 双 SX1278 实物对打验收（用户两根现成） | 语音/图像上报（传感器只有温湿压 v1） |

**层次选择**：协议层做"≤120B 二进制帧"（dcp 结论：MCU 跑不了 MQTT 的开销）；物理层用现成模块不做射频设计；固件用 Arduino-ESP32 + RadioLib（生态成熟，比 ESP-IDF 上手快——mesh_layer 是 ESP-IDF 的，v2 融合时再迁）。

## 二、架构设计（P2 层次 / P1 关系）

```
[节点 ×N]                    [网关 ×1]                     [主机]
ESP32-S3 SuperMini      ESP32-S3 SuperMini
+BME280 +OLED           +SX1278                       冥王峡谷/天选7/云服
+SX1278                  │                              │
   │ LoRa 433MHz 星型     │ USB串口 / WiFi MQTT          │ rf_brain 订阅
   └────── 30s 一帧 ──────┴───── JSON {node_id,t,h,p,rssi} ─┴→ AI 感知/告警/日志
```

**LoRa 帧格式（dcp 风格，≤120B 载荷）**：
```
[0xD0 0xCC] [type:1] [seq:1] [node_id:1] [payload:N] [crc16:2]
type: 0x01=env 0x02=heartbeat 0xFE=ack 0xFF=err
payload(env): t:int16(0.01℃) | h:uint8(0.1%) | p:uint32(0.01hPa)
```

**上行（网关→主机）**：USB 串口 JSON `{"node_id":1,"t":26.3,"h":55.0,"p":1013.2,"rssi":-87}`；WiFi MQTT topic `loracanary/<node_id>`（网关 ESP32-S3 自带 WiFi，接到路由器；无 WiFi 时串口足够）。

## 三、施工步骤（工单 AA 与硬件并行）

1. **AA-01 节点采集+显示**：BME280 采集 → OLED（SSD1306 0.96"）→ 串口 JSON debug
2. **AA-02 LoRa 帧收发**：帧编解码（Python 实现一份用于测试）+ RadioLib SX1278 收发 + 2 次重传
3. **AA-03 网关上行**：LoRa 收帧 → 解析 → 串口 JSON + WiFi MQTT 发布（MQTT 库 PubSubClient）
4. **AA-04 测试+文档**：pytest 帧编解码（Python 侧镜像实现）/坏帧/CRC 丢弃/重传；README + 真机验证步骤
5. **硬件 PCB（用户，与 AA 并行）**：嘉立创 EDA 专业版画模块化底板 + AI 布局（见第六节）

## 四、关键假设与 fallback（P1 关系，表格）

| 假设 | 若不成立 |
|---|---|
| 两根 SX1278 + 两块 ESP32-S3 可实物对打 | 无实物时用 RadioLib 环回（TX→RX 同模块）验收协议层，真机验证点留给用户 |
| GY-BME280-5V 与 GY-BMP280 均可用（I2C 0x76/0x77） | 自动探测地址；两个都没有时用 mock 数据（诚实标注 MOCK） |
| 433MHz ISM 频段合法可用（业余 70cm 频段内） | 遵守法规，功率 ≤100mW 默认配置 |
| Arduino-ESP32 + RadioLib pip/库可装 | 库装不上换 ESP-IDF + 已有 mesh_layer 的 Radio 驱动（meshtastic-对照-报告 有对比） |
| 宿舍/家里 LoRa 通距（几百米内） | 上报失败重试 2 次后丢弃+心跳计数，不阻塞 |

## 五、已知限制（诚实标注）

1. v1 星型单跳，节点数 ≤32（node_id 1B），范围受 433MHz 视距限制（市内几百米）
2. 明文帧，仅 CRC 防错不防恶意（v2 加 AES-128，密钥出厂写死）
3. 传感器仅温湿压；光照/人体（GY-30/HC-SR501 用户有）v2 加 type 扩展
4. 无低功耗深度睡眠优化（18650 供电场景先跑通）；省电 → v2 定时唤醒
5. PCB 底板为模块化设计，BOM 主要是排母/插座/电源件，不含射频匹配（射频由模块承担）

## 六、硬件 PCB 约束（用户·嘉立创 AI 试水）

**模块划分（抄立创 robba LoRa 装置结构，风险最低）**：
```
Type-C(5V) → TP4056 锂电池充电 → 18650 电池 → AMS1117-3.3 LDO → 3.3V 轨
                                                          ├→ ESP32-S3 SuperMini 排母
                                                          ├→ SX1278 LoRa 模块 排母
                                                          ├→ BME280 模块 排母
                                                          └→ OLED 0.96" 排母 + BOOT/RST按钮 + LED
```
可先做**纯底板 v0.5**（不做充电，18650 靠 AMS1117 直供 3.3V+USB-C 5V 供电切换），充电板 v1 再加——试水第一批越简单越好。

**嘉立创 AI 提示词要点（直接复制给 AI）**：
- "2 层板，60×50mm；电源区（TP4056/AMS1117）放左下角，远离天线区；SX1278 模块排母放右上角，天线位伸出板沿 ≥5mm 净空；ESP32-S3 排母居中；OLED/BME280 排母在右侧；3.3V 电源走线 ≥0.5mm；每个排母旁放 100nF 退耦；底部铺地，天线投影区禁铜"
- 布局完成后跑 DRC 到 0 错误再下单；AI 布局只当草稿，人眼复核电源/天线两个关键区

## 七、测试用例（纯 Python 优先）

1. 帧编码往返：encode(env) → bytes → decode → 字段一致
2. 帧类型分派：env/heartbeat/ack/err 各一
3. 坏帧：magic 错 → 丢弃
4. CRC 错误 → 丢弃并计数
5. 超长 payload → 拒绝（≤120B）
6. seq 乱序/重复 → 日志记录不崩溃
7. 重传逻辑：无 ACK → 重发 ≤2 次后放弃
8. 采集 mock：BME280 不可用 → MOCK 数据 + 标注
9. 地址探测：0x76/0x77 自动探测日志
10. 网关 JSON 输出格式校验（可被 python json.loads 解析）
11. OLED 显示 mock：无屏不崩溃
12. RadioLib 环回：同一模块 TX→RX 收到自己帧

## 八、交付物清单

- 节点固件（Arduino 工程：采集/OLED/LoRa）+ 网关固件（串口/MQTT）
- `tools/lora_frame.py` 帧编解码镜像（供 pytest + 主机解析）
- tests ≥12（pytest 全绿）
- README（烧录/接线/真机验证步骤）
- SPEC 硬件约束文档（用户画 PCB 用）

## 九、验收标准（可执行不变量）

```bash
# 1. 帧编解码正确
cd tools && pytest -q                          # ≥12 passed
python -c "from lora_frame import encode,decode; b=encode(env=1,t=26.3,h=55,p=1013.2); d=decode(b); assert abs(d['t']-26.3)<0.01 and d['node_id']==1; print('OK')"
# 2. 坏帧贞洁（不强解）
python -c "from lora_frame import decode; assert decode(b'\x00'*10) is None; print('OK')"
# 3. 协议在代码里真实存在
grep -n "0xD0.*0xCC\|0xD0CC" tools/lora_frame.py 固件库 2>/dev/null | head -3   # 非空
# 4. 网关 JSON 合规
grep -n 'json.dumps\|{"node_id"' 网关固件代码 | head -3                      # 非空
# 5. 无 LLM 调用
grep -rn "requests.post\|openai\|anthropic" 固件+工具代码                     # 空
```

**真机验证点（用户，留实测量）**：两块 ESP32-S3 + 两根 SX1278 对打——节点放窗台、网关插主机，30s 内主机收到 `{"node_id":1,"t":..,"h":..,"p":..}`；天线拉开 5m 以上测通断；PCB 打样焊好后跑同样链路。

## 十、提交规范

- 分项 commit：`feat(loracanary):` 前缀（AA-01~04 各一）+ `docs(loracanary):` README
- 成果推 `trae/agent-aa` 分支
- 中文注释/输出；阻塞（库装不上/无实物）不硬做，写清原因返回

## 十一、工单划分

固件单线 AA 工单（AA-01~AA-04 顺序做，量约几百行，一个智能体一轮完成）：完整任务见 `TRAE_WORKORDER_PROMPT_AGENT_AA.md`。硬件 PCB 用户自做（第六节约束），不占工单。