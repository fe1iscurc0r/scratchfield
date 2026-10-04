# SPEC-20 v1.5 · PCB Board1 操作记录（AB 线 · v2 定稿版）

> 日期：2026-08-29 · 工具：easyeda-agent CLI（typed action + debug exec）· 项目：`LoRaCanary-底板-v0.6`
> 铁律遵守：**原 PCB2（AA 线成品，27 器件 314 段走线）全程只读，未动一笔**。
> 当前版本：**4 层板**（Top/Bottom 信号 + Inner1=GND 内电层 + Inner2=3V3 内电层），布局为用户手调定稿，信号走线由用户继续手工布线。

## 一、版本历史

| 版本 | 内容 | 状态 |
|---|---|---|
| v1（已废弃） | PCB2 原条带布局 + 外挂 J2/J3，10×10cm 板框 | 布局被评「太空」，推倒重排 |
| **v2（当前）** | 全板按功能分区重排 + 扩展包 7 件 + 用户手调 + 4 层叠层 | 走线待用户手工收尾 |

## 二、v2 版图（用户手调定稿，39 器件）

- **主控区（中偏左）**：J2A + J2B = 两条 1×8 直插排母（HMT-2.54-1*8PM，C54620384），**排间距 18mm（709mil）**，对应合宙 ESP32-C3 插接模块的两排插针；U1 = S3 SuperMini 2×17 排母在 J2B 右侧
- **射频区（右下）**：U2 = SX1278 Ra-01 模块排母，天线端朝板缘；**J3 = GPS 四接口排母在左上对角**（与 433MHz 天线距离最大化）
- **显示（右上）**：U6 = 0.96" OLED 4P
- **传感扩展（顶部一排）**：J4 = GY-30/BH1750 光照 1×5（I2C，ADDR 接 GND=0x23）、J6 = 通用 I2C 1×4、J5 = HC-SR501 人体感应 1×3（**VCC 走 5V_EXT 防护轨**）、J8 = 备用 1×2（PIR_OUT/USER_BTN 转接）
- **电源区（左下）**：J1 USB-C → U5 TP4056 → U4 AMS1117 → 3V3；B1 电池座左缘；R9/R10 = 100kΩ×2 电池电压分压（BAT+→VBAT_ADC）；F1 = ASMD1206 自恢复保险丝 0.5A + D2 = SMAJ5.0A TVS 构成 5V_EXT 防护轨（供 J5 外设）
- **其他**：SW3 用户按键（USER_BTN）、SW1/SW2（BOOT/EN）、四角 M3 安装孔

## 三、4 层叠层与平面去耦

| 层 | 内容 |
|---|---|
| Top / Bottom | 信号走线；5V / VBUS 也在这两层走铜线（power-planes 分配为「走线」而非平面） |
| Inner1 | **GND 内电层**（平面铜已铺） |
| Inner2 | **3V3 内电层**（平面铜已铺） |

- 3V3 轨去耦电容 C1/C5（100nF）+ C3（10µF）焊盘脚下已由工具打出**成对过孔直连两个内层平面**（pad→via→plane，最小回路电感，标准 4 层去耦拓扑）；C2/C4 在 VBUS 侧不进平面
- 全板 81 过孔中 69 个为**平面缝合孔（已锁定，rip-up 安全）**；C1/C3/C5 去耦孔对核验完好
- 信号走线基线由 route-short/route-critical 预布（约 370 段），**最终走线由用户手工调整**（AB 智能体按指示不再动线）

## 四、J2A/J2B 网络映射（⚠️ 引脚序为假设，装配前必须对照合宙模块实物丝印核对！）

| J2A pad | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 网络 | 5V | GND | 3V3 | （空，EN） | VBAT_ADC | GPS_PWR | GPS_TX | GPS_RX |
| C3 语义 | 5V | GND | 3V3 | EN | IO0 | IO1 | IO2 | IO3 |

| J2B pad | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| 网络 | SDA | SCL | LORA_MOSI | LORA_MISO | LORA_SCK | LORA_NSS | LORA_DIO0 | LORA_RST |
| C3 语义 | IO4 | IO5 | IO6 | IO7 | IO8 | IO9 | IO10 | IO11 |

其他插接件：J3（GPS）`1=3V3 2=GND 3=GPS_TX 4=GPS_RX`；J4（GY-30）`1=3V3 2=GND 3=SDA 4=SCL 5=GND(ADDR)`；J5（HC-SR501）`1=5V_EXT 2=GND 3=PIR_OUT`；J6/J8 见第 二 节。**所有排母的 pin1 丝印标记装配时核对方向。**

## 五、遗留问题清单（等用户回来处理，AB 未擅动）

1. **内层平面 vs THT 焊盘间距 ×6**（DRC）：PIR_OUT 等 6 个通孔焊盘穿过 GND 内电层，反焊盘间隙仅 ~0.78mm。修法：`pcb drc-rules-set` 抬高平面隔离间隙后 `pour-rebuild`，或手工放大该焊盘反焊盘。
2. **天线禁布区丢失**：antenna-keepout 之前生成的禁铜区在后续操作中没了（region=0）。U2 模块天线端附近手工布线时避开铺铜/走线；或回来后重跑 `pcb antenna-keepout`。
3. **Netlist Error ×1**：11 个新增件（J2A/J2B/J4/J5/J6/J8/SW3/R9/R10/F1/D2）只在 PCB 侧无原理图孪生；要消除需补画进原理图后 `pcb sync-designators`/`import-changes`。
4. **Board Outline to SMD Pad ×16**：AA 线原设计遗留（近板框焊盘），非本次引入；打样前可顺手内收。
5. **引脚方向核对**（用户强调）：J2A/J2B 引脚序是按 C3 固件 GPIO 语义的假设排布；所有插接件 pin1 方向、F1/D2 极性、B1 电池极性装配前逐一对照实物。
6. 顶层/底层目前无 GND 覆铜（GND 在 Inner1 平面）；如需外层 GND 铺铜可加 `pour-fit --net GND --layer 1/2`，属于「铺铜」范畴，未擅动。

## 六、验证状态

- 门禁全过：分档 1-4 / 布局指纹（39 件）/ 板框 / pre_route（`layout-lint --gate --min-score 0 --max-crossings -1`，几何 0 短路 0 重叠 0 出框 0 紧凑）
- 铺铜已重建（6 块内层平面）；已存盘；快照见 `docs/assets/loracanary-v1.5-board1-snapshot.png`（v1 版快照，v2 快照路径见嘉立创 artifacts）
- 打样参数建议：4 层 100×100mm，沉金；Inner1/Inner2 平面已含反焊盘
