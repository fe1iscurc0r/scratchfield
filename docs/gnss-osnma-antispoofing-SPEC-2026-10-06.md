# GNSS OSNMA 反欺骗线 SPEC v1

> 工单202 任务二落地（轮32 P0-1）· 出稿 2026-10-06 · 来源：`docs/授粉轮32-GNSS定位安全候选-授粉报告-2026-10-04.md`
> 定位：频谱哨兵线的**唯一天然加密认证源**——gnss spoofing detection 生态（搜"GNSS spoofing detection"最高 6★ 全是 ML 玩具）与正规实现之间的空白桥梁。

## 0. 一句话

用 SDR（或支持 OSNMA 的 u-blox 模块）采集 Galileo E1-B 的 OSNMA 认证数据，
经 TESLA 密钥链 + ECDSA 公钥验证导航电文的真实性，把「这颗卫星是真的」变成
**可进频谱哨兵事件流的结构化可信度信号**——欺骗/伪造从「怀疑」变成「证据」。

## 1. 协议要点（已核验事实，2026-10-06）

| 事实 | 值 | 备注 |
|---|---|---|
| 服务状态 | **Initial Service 已于 2025-07-24 宣布运行** | 全球免费；不再是测试期 |
| 承载位置 | E1-B **I/NAV 的 40-bit 保留字段** | 向后兼容旧 ICD，零系统开销 |
| 字段划分 | **HKROOT 8 bit**（全局头 + DSM 数字签名消息）+ **MACK 32 bit**（MAC + 延迟披露密钥） | 每 I/NAV 页 2 s → OSNMA 净荷 20 bps |
| E1-B 数据率 | 125 bps | 签名必须短 → 故用 TESLA 而非纯公钥签名 |
| 密码算法 | SHA-256 / SHA3-256 / HMAC-SHA-256 / CMAC-AES-256 / ECDSA P-256(SHA-256) / ECDSA P-521(SHA-512) | 实现细节全在 OSNMA ICD |
| 信任锚 | **Merkle 树根**（一次性装载）→ 验公钥 → 验 TESLA Root Key → 验链上密钥 | 密钥材料从 GSC 网站 / SFTP 或 SIS 获取 |
| 时间同步 | **必须 30~300 s 内**（取决于工作模式），延迟披露协议 | 时间不可信 = 认证不可做 |
| 广播范围 | OSNMA 字段**仅部分卫星**播发；其余卫星该字段全零（须丢弃） | 支持跨星认证（任一可见星可分发密钥） |
| 前置校验 | 认证只对 **CRC 通过**的 I/NAV 页进行 | 数据先过 I/NAV CRC |

> 权威文本：Galileo OSNMA SIS ICD + OSNMA Receiver Guidelines（GSC 电子库）；
> 参考实现：`daniestevez/galileo-osnma`（89★ Apache-2.0，**Rust 核心 + C/C++ API**，卫星接收圈权威作者；最后 push 2026-03-04）。

## 2. 硬件能力矩阵（铁律：先认能力，再谈架构）

| 设备 | 收 Galileo？ | 收 OSNMA？ | 在本架构中的**真实**角色 |
|---|---|---|---|
| **NEO6M**（u-blox 6 代） | ❌ 仅 GPS L1 C/A（QZSS） | ❌ | **对照/受害机**：GPS-only 基线；用于「欺骗演示」中被带偏的一方，与 OSNMA 路径互证 |
| **RTL-SDR**（R820T2，2.4 Msps） | ✅ 可收 E1 主瓣（截断） | ✅（经软件解调） | **路径 A 最低配采集源**（灵敏度损失需实测，见 §3.1 边界） |
| **IC-705** | ❌（不含 1575 MHz 下变频至可解调链路） | ❌ | 干扰监测侧：GNSS 干扰/jamming 频谱确认（L1 带内能量异常） |
| u-blox **M9N / F9P**（需采购） | ✅ | ✅（固件支持） | **路径 B 主力**：芯片内完成 OSNMA，UBX 直出认证状态 |
| Airspy Mini / USRP / bladeRF（可选） | ✅ 带宽充裕 | ✅ | 路径 A 升级，摆脱 RTL-SDR 带宽约束 |

**⚠️ 铁律一**：NEO6M 不参与 OSNMA 数据链——它连 Galileo 都不接收。
**⚠️ 铁律二**：`laika` 面向 UBX-RXM-**RAWX**（M8 及以上世代）；NEO6M 的观测量格式为 v6 的
UBX-RXM-RAW，**能否被 laika 直接吃需实测**（M1 阶段验证项，不行则升级模块或走 RTL-SDR 观测量）。

## 3. 采集路径

### 3.1 路径 A：RTL-SDR 软件接收（零新增硬件，M1 主线）

| 参数 | 取值 | 依据 |
|---|---|---|
| 中心频率 | **1575.42 MHz**（Galileo E1） | E1 标称 |
| 采样率 | **2.4 Msps（上限档）**；理想 ≥4 Msps | BOC(1,1) 主瓣 ±2.046 MHz；RTL-SDR 截断主瓣 → **灵敏度损失，需实测确认能否稳定解 I/NAV** |
| 增益 | 手动 30~40 dB（关 AGC，避免强信号阻塞） | 弱 GNSS 信号惯例 |
| 带宽 | 与采样率联动（R820T2 最窄 0.2 MHz 档不适用，取最大） | — |
| 采集时长 | ≥ 300 s 连续（时间同步 + 密钥链跨页拼接需要） | OSNMA 跨页/跨星拼接要求 |
| 输出 | IQ 基带记录（.cu8/.wav）+ 卫星列表日志 | 供 `gnss-sdr` / galileo-osnma 接收链回放 |

**若 M1 实测 RTL-SDR 无法稳定出 I/NAV**：路径 A 升级档位（Airspy Mini ≥6 Msps）或直接转路径 B。
不得含糊表述「RTL-SDR 能收」——**能收主瓣 ≠ 能稳定解调**，以实测为准。

软件链：`librtlsdr` 采集 → GNSS-SDR（或 galileo-osnma 自带接收链）解 E1-B I/NAV → 提取 40-bit OSNMA 字段 → `galileo-osnma`（Rust 核心，C/C++ API 供胶水层）验签。
时间同步：接收机侧对 Galileo System Time（GST）估计误差须 <300 s，由 I/NAV 的 TOW + 本地时钟粗同步满足。

### 3.2 路径 B：u-blox OSNMA 接收机（芯片内认证，工程最稳）

适用模块：M9 / F9 / X20 / F10（"上线首日支持"）；ZED-F9P 需 **固件 HPG 1.51+**，ZED-F9T 需 **TIM 2.24+**。

```
CFG-GAL-USE_OSNMA        = 1       # 启用 OSNMA
CFG-GAL-OSNMA_TIMESYNC   = 1       # 时间同步使能
CFG-GAL-OSNMA_MINTAGLENGTH = 80    # 最小 tag 长度
CFG-GAL-OSNMA_INAVPRIM   = 1       # I/NAV 优先
CFG-NAVSPG-ONLY_AUTHDATA = 1       # 只用已认证数据（可选，激进档）
```
密钥装载（**密钥不在固件里**，须注册 GSC 获取）：
`UBX-MGA-GAL-OSNMA_MERKLE`（Merkle 根）+ `UBX-MGA-GAL-OSNMA_PUBKEY`（公钥+PKID+哈希算法）+
`UBX-MGA-INI-TIME_UTC/GNSS`（带 trusted flag 的可信时间，保护首认证窗口）。
状态读取：`UBX-NAV-SIG`（信号认证状态）/ `UBX-NAV-TIMETRUSTED` / **`UBX-SEC-OSNMA`**（认证明细）。

## 4. 依赖清单

| 组件 | 许可 | 用途 | 安装口径 |
|---|---|---|---|
| `daniestevez/galileo-osnma` | Apache-2.0 | OSNMA 验签核心（Rust + C/C++ API） | `cargo` 构建；或引 C API 做胶水 |
| GNSS-SDR（可选） | GPL-3.0 ⚠️ | E1 软件接收链 | **仅二进制/独立进程使用，不并入本仓代码树**（copyleft 红线）；或走 galileo-osnma 自带接收链 |
| `rtl-sdr` / `librtlsdr` | GPL-2.0 ⚠️ | RTL-SDR 驱动 | 系统级驱动，独立使用，不入仓 |
| `commaai/laika` | **MIT ✅** | 观测量→位置/残差处理底座（Astrodog 修正流水线） | `pip install laika`；修正数据在线拉取（运行依赖） |
| `pyubx2` | BSD-3 ✅ | 路径 B 的 UBX 报文收发 | `pip install pyubx2` |
| GSC 密钥材料 | 官方分发 | Merkle 根 / 公钥 / 证书 | GSC 网站 + OSNMA SFTP（需注册，人工一次性） |

**红线**：GPL 系（GNSS-SDR/rtl-sdr 驱动）只以**进程外二进制**形态使用，不复制任何代码入本仓。

## 5. 验签流程（接收机侧，与 ICD 对齐）

```
1. 收 E1-B I/NAV 页 → CRC 校验（失败即弃）
2. 抽 40-bit OSNMA 字段 → 全零则丢弃（该星未播 OSNMA）
3. HKROOT：收 DSM → 用已装载公钥（ECDSA P-256/521）验 TESLA Root Key → 信任链起点
4. MACK：收 (MAC, 延迟密钥) → 用链上前序密钥验当前密钥的哈希链归属
5. 用验证过的密钥重算 MAC → 与收到的 MAC 比对 → 页面级认证结论
6. 页面级结论聚合到「卫星级 + 电文级」可信状态，附时间同步质量
   失败路径：时间超窗 / 缺少信任锚 / 密钥链断裂 → 状态必须显式 unknown，不得默认可信
```

## 6. 与频谱哨兵线的对接面（本 SPEC 的核心产出）

### 6.1 事件契约（NDJSON，与 rf_brain `sentinel_ingest` 同构）

```json
{"src":"gnss-osnma","ts":"2026-10-06T12:00:00Z","svid":11,"constellation":"GAL",
 "auth":"ok|fail|unknown","reason":null,"trusted_time":true,"time_err_s":0.4,
 "mack_ok":true,"dsm_ok":true,"sat_count_auth":6,"sat_count_seen":14}
```
- 逐页事件（高频，可采样）+ 卫星级聚合（每 30 s 一条）。
- `auth=fail` 需附 `reason`（如 `mac_mismatch` / `chain_broken` / `time_out_of_window`）。

### 6.2 融合点（三处，按侵入性递增）

| 融合点 | 做法 | 阶段 |
|---|---|---|
| **事件入流** | NDJSON 走 `sentinel_ingest` 进 rf_brain 记忆库，`protocol=gnss-osnma` | M2 |
| **可信度面板** | 聚合出「GNSS 信号可信度」指标（认证星数/可见星数 + 时间同步质量），与频谱干扰事件并排 | M2 |
| **联合判定** | IC-705 频谱侧（L1 带内能量异常/jamming）∧ OSNMA 认证失败 → 升级为 P0 告警；仅频谱异常 → P1 | M3 |

### 6.3 告警分级

| 级 | 条件 | 动作 |
|---|---|---|
| **P0** | 认证失败（MAC 不匹配/链断裂）且有频谱异常佐证；或时间同步被推离窗口 | 立即告警 + 冻结定位输出（对接无人机/定位消费者） |
| **P1** | 认证失败无频谱佐证（可能是配置/密钥过期）；OSNMA 中断 > 5 min | 告警 + 降级为「仅 GPS 对照」模式 |
| **P2** | 认证星数下降（< 阈值）/单星丢失 | 记录，不告警 |

## 7. 分阶段落地

| 阶段 | 内容 | 验收 |
|---|---|---|
| **M1（本 SPEC 后第一个动作）** | RTL-SDR 采集 300 s E1 IQ 落盘；尝试解 I/NAV 出卫星号；同时验证 NEO6M/laika 的 RAWX 兼容性 | IQ 可回放；至少有卫星的 I/NAV 解出（能出 svid 即算）；laika 兼容性给出**明确结论**（支持/不支持/需换模块） |
| **M2** | 接 galileo-osnma 验签 → NDJSON 事件入 rf_brain | 认证事件可在记忆库查到；`auth` 字段有真实 ok/unknown（测试期/室内允许 unknown，但**不得伪造 ok**） |
| **M3** | 与 IC-705 频谱侧联合判定 + 面板 | 构造一次受控欺骗演示（如 SDR 发射伪 GPS 信号干扰 NEO6M，验证 OSNMA 路径不跟随） |

## 8. 验收标准（对齐工单）

- [x] SPEC 落 `docs/`，含采集参数 / 依赖清单 / 与频谱哨兵对接面 ← 本文件
- [ ] M1 实测记录（IQ 采样 + 解调结论 + laika 兼容性结论）
- [ ] M2 验签链路端到端 ≥1 条真实认证事件入流

## 9. 风险与未决项（诚实清单）

1. **RTL-SDR 带宽是最大技术风险**：2.4 Msps 对 E1 BOC(1,1) 主瓣截断，灵敏度损失量级未实测——M1 必须先出这个结论，不许先写"能收"。
2. **GSC 注册与密钥材料获取是人工依赖**（需账号 + 一次性下载），自动化不了；密钥轮换（Merkle 树更新）需关注 GSC 公告。
3. **室内/城市峡谷环境 OSNMA 星数可能为 0** —— 演示须在开阔天空；M2 的验收要在室外完成。
4. **时间同步是硬门槛**：无可信时间源时首认证窗口（30~300 s）可能失败，路径 B 需 `UBX-MGA-INI-TIME_*` 辅助。
5. **GNSS-SDR 为 GPL-3.0**：进程隔离使用；若未来要并入产品分发，需替换为宽松许可接收链（自研或 galileo-osnma 自带链）。
6. NEO6M+laika 的 RAW 兼容性未验证（§2 铁律二）——M1 出结论，不行则列入模块升级建议。
