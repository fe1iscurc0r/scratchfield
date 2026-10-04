# R53 ExpressLRS / OpenRX 超远距离 LoRa 链路勘察报告

> 生成：2026-08-31 · 来源：github.com/OpenDrone-hw/OpenRX + github.com/ExpressLRS/ExpressLRS（2026-08-31 浅克隆源码勘察）
> 目标：把 ELRS 4.0 的超远距离 LoRa 链路设计（100km+ @1W）映射到 LoRaCanary 433 MHz 链路，产出 ≥3 条可借鉴点。
> 状态：勘察完成（报告）

---

## 0. 结论速览

ExpressLRS（ELRS）与 OpenRX 是「LoRa 物理层 + 极简空中包 + FHSS 跳频」三条腿撑起来的高可靠 RC 链路：**用 LoRa 的扩频增益换链路预算，用砍到极致的包结构换延迟，用伪随机跳频换抗干扰与合规性**。对 LoRaCanary 433 MHz 链路最可迁移的三点是：

1. **FHSS 跳频 + 低信道数合规域表**（含 433 MHz 域，3/8/20 信道）——LoRaCanary 当前固定频率，引入跳频可在不增发射功率的前提下提升抗干扰/抗多径，并天然满足占空比合规。
2. **按链路预算分级的 LoRa 参数表（SF/BW 档位 + 包结构削减）**——ELRS 把「低延迟」与「远距离」做成同一物理层上的不同参数档，LoRaCanary 可直接套用 SF/BW/CR 三参数与「缩短前导+减小 CRC+去掉包头」的包瘦身。
3. **接收机射频前端的分立 PA/LNA + 双通道 LR1121 结构**（OpenRX Mono/Gemini）——LoRaCanary 若要上 433 MHz 远距，参考其 RFX2401C PA/LNA + SKY13373 开关 + IPD 匹配链，可把 telemetry 从 20 mW 提到 158 mW 量级。

下面分四节展开：硬件勘察、链路机制、链路预算、借鉴清单。

---

## 1. OpenRX 接收机硬件勘察

OpenRX 是 OpenDrone-hw 的开源 ExpressLRS 接收机家族，四款变体共用 ESP32-C3 核心与 ELRS 统一固件，只在射频 IC / 频段 / 前端 / 天线上分叉：

| | Lite | Lite-UFL | Mono | Gemini |
|---|---|---|---|---|
| 频段 | 2.4 GHz | 2.4 GHz | 双频 | 双频 + Xrossband |
| 射频 IC | SX1281 | SX1281 | LR1121 | 2× LR1121 |
| 天线 | 板上陶瓷 | U.FL | U.FL | 2× U.FL |
| Telemetry 功率 | 13 dBm (20 mW) | 13 dBm | 最高 22 dBm (158 mW) | 最高 22 dBm |
| MCU | ESP32-C3 | ESP32-C3 | ESP32-C3 | ESP32-C3 |
| 协议 | CRSF | CRSF | CRSF | CRSF |

关键架构事实（来自 `AGENTS.md` 技术说明）：

- **时钟**：SX1281 变体用 52 MHz TCXO，LR1121 变体用 32 MHz TCXO；TCXO 提供比晶振更稳的频率基准，直接关系到 LoRa 频偏容限（见 §2.3）。
- **RF 链（Mono 单 LR1121 双频）**：
  - 2.4 GHz：`LR1121 RFIO_HF → 滤波器 → RFX2401C (PA/LNA) → SKY13373 开关 → U.FL`
  - Sub-GHz TX：`LR1121 RFO_HP_LF → IPD (T1) TX_HP → SKY13373 → U.FL`
  - Sub-GHz RX：`U.FL → SKY13373 → IPD RX → LR1121 RFI_P/N_LF`
  - LR1121 低功率 PA 端口未接——ELRS 从不用低功率档。
- **前端由射频 DIO 直驱**（非 ESP32 GPIO）：DIO5=RFX2401C RXEN、DIO6=TXEN、DIO7/8=SKY13373 切换。Gemini 双射频对称布线，一套开关表服务两颗射频。
- **已知失配保留**：2450FM07D0034T 滤波器 pin1 为 40 Ω（为 SX128x 设计），LR1121 RFIO_HF 为 50 Ω，产生约 19 dB 回损（VSWR 1.25）、0.05 dB 失配损耗——相对滤波器自身 14 dB 典型回损可忽略。

对 LoRaCanary 的硬件启示：**433 MHz 远距链路不能只靠一颗裸收发芯片，需要「PA/LNA 前端 + 收发开关 + 阻抗匹配」三板斧**；OpenRX 的 RFX2401C（2.4G）/LR1121 内置 sub-GHz PA 结构给出了可直接参照的前端拓扑。

---

## 2. ExpressLRS 链路机制（ELRS 4.0）

### 2.1 物理层：LoRa + FLRC 双调制

ELRS 基于 Semtech SX127x（sub-GHz，如 433/868/900 MHz）/ SX1280（2.4 GHz）LoRa 硬件，核心是 **LoRa 调制 + 极简包结构**：

- **LoRa 扩频因子档位**（SX1280 侧，`SX1280_Regs.h`）：`SF5~SF8`；对应符号时间（812.5 kHz BW 下）：SF5=39.4 µs、SF6=78.8 µs、SF7=157.6 µs、SF8=315.2 µs（`lib/LBT/LBT.cpp` 实测有效等待含 60 µs 收发切换）。sub-GHz 侧 LR1121 支持到 `SF5~SF12`，BW 从 10.42 kHz 到 41.67 kHz（`LR1121_Regs.h`）。
- **带宽档位**（SX1280）：200 / 400 / 800 / 1600 kHz。
- **ELRS 4.0 引入 FLRC 调制**（`SX1280_PACKET_TYPE_FLRC`）：在 2.4 GHz 高数据率档用于进一步压缩包时长；GFSK/LoRa/Ranging/FLRC/BLE 五种包类型都已在驱动层就位。
- **包结构削减**（README 明示「highly optimized over-the-air packet structure」）：极短前导、CRC 最小化、包头省略，是「同时拿距离和低延迟」的关键——LoRa 的同步前导在低数据率下会吃掉大量空中时间，砍短它即可在同码率下翻倍包率。

### 2.2 FHSS 跳频 + 占空比合规（LBT）

- `lib/FHSS/FHSS.cpp` 内置**分域跳频表**，2.4 GHz 域 80 信道；sub-GHz 各域信道数很少——**这正是合规的关键**：

| 域 | 起止 | 信道数 |
|---|---|---|
| AU433 | 433.42–434.42 MHz | 3 |
| EU433 | 433.10–434.45 MHz | 3 |
| US433 | 433.25–438.00 MHz | 8 |
| US433W | 423.5–438.0 MHz | 20 |
| EU868 | 863.275–869.575 MHz | 13 |
| 2.4 GHz | 2400.4–2479.4 MHz | 80 |

- 跳频序列由 bind phrase 派生的伪随机序列驱动（`FHSSsequence[]`），收发双方无需逐信道协商即可同步跳频。
- **LBT（Listen Before Talk）**（`lib/LBT/LBT.cpp`）在 `Regulatory_Domain_EU_CE_2400` 下启用：发射前用瞬时 RSSI 判忙，等 SF 相关的有效 RSSI 建立时间（SF5≈100 µs … SF8≈480 µs）再决定是否发射，用于满足欧洲 CE 占空比/先听后说要求。

对 LoRaCanary：**433 MHz ISM 域同样有占空比/信道数约束**，ELRS 的「低信道数域表 + LBT」是现成合规范本。

### 2.3 频偏估计与时钟

- LoRa 调制本身对频偏有天然容限（扩频增益稀释了频率误差），但 ELRS 的链路预算天花板由**晶振精度**决定：OpenRX 用 TCXO（52 MHz / 32 MHz）而非裸晶振，把收发频偏压到 LoRa 解调器的捕获范围之内。
- 接收侧 RSSI 是「解扩后」估计（LR1121 注释：SignalRssiPkt 为去扩后估计），配合 `LQCALC`（链路质量滑动平均）做逐包链路质量评估，供上层做功率/速率自适应。

---

## 3. 链路预算分析（100 km+ @1W 的可行性）

以 LoRaCanary 目标频段 433 MHz 与 ELRS 2.4 GHz / 900 MHz 对照，用自由空间损耗公式
`Lfs(dB) = 20·log10(d_km) + 20·log10(f_MHz) + 32.44` 估算 100 km 处的路径损耗：

| 频段 | f (MHz) | Lfs@100km (dB) | 相对 433 MHz |
|---|---|---|---|
| 433 MHz | 433 | **125.2** | 0（基准） |
| 868 MHz | 868 | 131.2 | +6.0 |
| 900 MHz | 915 | 131.7 | +6.5 |
| 2400 MHz | 2440 | 140.2 | +15.0 |

**结论：同样 100 km，2.4 GHz 比 433 MHz 多 15 dB 路径损耗**。ELRS 在 2.4 GHz 上打 100 km+ 靠的是：1 W（+30 dBm）发射功率 + 高增益定向天线 + LoRa 高扩频档（SF8）+ 极低数据率。433 MHz 天然省下 15 dB，意味着 LoRaCanary 用**更低的发射功率或更小的天线**即可达到同等链路预算——这是 ELRS 经验向 433 MHz 迁移的最大红利。

链路预算模板（接收灵敏度为 LoRa SF/BW 的典型数量级，实测需以芯片 datasheet 为准）：

```
RX_sensitivity = -174 + 10*log10(BW_Hz) + NF + SNR_required(SF)
margin(dB) = Ptx(dBm) + Gtx + Grx - Lfs - Lmisc - RX_sensitivity
```

- SF 每升 1 档，灵敏度约改善 2.5 dB（代价是符号时间翻倍、数据率减半）；
- 433 MHz 域信道窄（ELRS 表 3/8/20 信道），可安心用窄 BW（如 125 kHz 甚至 62.5 kHz）换取额外灵敏度，而不像 2.4 GHz 那样必须用宽 BW 撑数据率。

---

## 4. 对 LoRaCanary 433 MHz 的可借鉴点清单（≥3）

### 借鉴点 1：FHSS 跳频 + 低信道数合规域表（P0 级价值）
- **ELRS 做法**：bind phrase 派生伪随机跳频序列，域表固化信道数（433 MHz 仅 3/8/20 信道），LBT 先听后说。
- **迁移到 LoRaCanary**：把固定频点改为 433 MHz 域内的 FHSS（3~8 信道足够），收发双方由共享密钥/序列号同步跳频；同时补 LBT（发射前 RSSI 判忙）满足 433 ISM 占空比合规。抗窄带干扰、抗多径衰落、合规性三方面一次性解决，且不需要增加发射功率。

### 借鉴点 2：LoRa 参数分档 + 包结构削减（P0 级价值）
- **ELRS 做法**：SF/BW/CR 三参数成档（SF5–8、BW 200–1600 kHz），「低延迟档 = 高码率短包 + 低 SF」与「远距离档 = 高 SF + 窄 BW」共存于同一物理层；空中包砍前导、砍包头、最小 CRC。
- **迁移到 LoRaCanary**：建立「速率/距离」参数表——远距档（SF12/BW125k/CR4_5 + 缩短前导），近距档（SF7/BW250k + 更短包）。包结构瘦身（固定长度、去掉逐包包头、CRC 降到 16 bit）可直接降低空中时间，提升同功率下的有效数据率与电池寿命。

### 借鉴点 3：接收机 PA/LNA 前端 + TCXO 频偏控制（P1 级价值）
- **ELRS/OpenRX 做法**：分立 RFX2401C PA/LNA + SKY13373 收发开关 + IPD 匹配链，把 telemetry 从 20 mW 提到 158 mW；用 TCXO（52/32 MHz）替代裸晶振压低频偏。
- **迁移到 LoRaCanary**：若 LoRaCanary 节点/网关需要反向 telemetry 或更远上行，参照该前端拓扑加 PA/LNA 与收发开关；网关端用 TCXO 提高频偏容限，避免高 SF（SF11/12）下因频偏超限而解调失败。

### 借鉴点 4（附带）：链路质量滑动平均驱动自适应（P2）
- **ELRS 做法**：`LQCALC` 对逐包 RSSI/SNR 做滑动平均，支撑功率/速率自适应决策。
- **迁移到 LoRaCanary**：LoRaCanary 已有 EWMA 可靠度机制（`tools/link_reliability.py`），可叠加**物理层 LQ（RSSI/SNR 滑动平均）**作为第二信号，与链路层 ACK 可靠度联合驱动 SF/功率自适应，避免「只按 ACK 丢包」反应滞后。

---

## 5. 勘察依据（文件定位）

- `OpenRX/README.md`：四变体规格表、协议 CRSF、telemetry 功率。
- `OpenRX/AGENTS.md`：架构、RF 链、时钟、前端 DIO 直驱、失配说明。
- `ExpressLRS/README.md`：LoRa + 极简包结构、2.4 GHz 1000 Hz / 900 MHz 200 Hz、CRSF/SBUS/MAVLink。
- `ExpressLRS/src/lib/FHSS/FHSS.cpp`：分域跳频表（含 433 MHz 域）。
- `ExpressLRS/src/lib/LBT/LBT.cpp`：LBT 占空比/先听后说、SF→符号时间。
- `ExpressLRS/src/lib/SX1280Driver/SX1280_Regs.h`：SF/BW/FLRC 包类型枚举。
- `ExpressLRS/src/lib/LR1121Driver/LR1121_Regs.h`：sub-GHz SF5–12、BW 档位。

---

## 6. 风险与待办

- **待实测**：接收灵敏度与链路预算中的 SF/BW 数值为 LoRa 典型量级，落地前需以 LoRaCanary 实际芯片（SX1276/1278 或同族）datasheet 校准。
- **433 MHz 合规**：ELRS 的 433 域表（3/8/20 信道）仅覆盖部分国家/地区，落地需按目标地区的 ISM 规则核对信道数、带宽与占空比。
- **FLRC 4.0**：FLRC 主要用于 2.4 GHz 高数据率档，对 433 MHz 远距链路借鉴价值有限，未在借鉴清单中展开。
