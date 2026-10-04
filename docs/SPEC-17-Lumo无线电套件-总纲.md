# SPEC-17 radio_suite 无线电套件 · 总纲 · v1

> 状态：待施工（2026-08-25 用户拍板：混合集成、集大之优点；许可松绑——AGPL 可吞 GPL；**独立组件 + 总线连接**）
> 用途：把主流无线电软件的**核心优点授粉集成**成独立组件 radio_suite——rf_brain 解码骨架 + rsba1_adapter（705 控制，RS-BA1 逆向成果）+ hamlog（日志）+ 哨兵网格（采集）+ 独立 UI；通过总线与工具注册连接陆墨/Hermes/冥王峡谷，不塞进任何 AI 壳（陆墨是陆墨，无线电是无线电）
> 读者：Trae（天选7）/ 沈遥 / 陆墨
> 依据：SPEC-18（科研增强）；rf_brain 解码器家族（aprs/psk31/ook）；rsba1_adapter（8 工具已建）；hamlog_adapter（已授粉，用户反馈"有很多问题"）；QEX《FT4/FT8 协议》（公开论文）

## 〇、一句话定位

**独立组件 + 总线连接**（用户拍板 2026-08-25：陆墨是陆墨，无线电是无线电）。无线电套件（radio_suite）是独立组件——解码、控制、日志、频谱自成一体，不塞进陆墨/lumo 壳；通过总线与工具注册暴露能力，陆墨/Hermes/冥王峡谷按需调用。陆墨是 AI 人格层，无线电是仪器层，两层解耦。

## 一、同类软件对比（选型依据）

### 1. 日志软件

| 软件 | 许可 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| Log4OM | 免费 | DXCC 追踪、集群集成、705 CAT 好 | 功能多学习曲线 | 功能集参考 |
| N1MM+ | 免费 | 比赛之王、高吞吐 | 比赛向，日常重 | 后置（打比赛再说） |
| HamRadioDeluxe | 商业 | 最强整体 | 收费 $99+/年 | 不采用，功能参考 |
| DXLab Suite | 免费 | DX 追踪强 | 套件复杂 | 功能参考 |
| Cloudlog | GPL-2.0 | 自托管 Web 日志 | PHP 栈 | 展示层思路参考 |
| **hamlog（我们）** | 已授粉 | 本地 SQLite、QSO/QSL 工具齐 | **用户反馈问题多**：无 ADIF 导入导出、无 DXCC 追踪、无 CAT 联动 | **升级对象** |

### 2. SSTV 软件

| 软件 | 许可 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| MMSSTV | freeware（不开放） | MMSSTV Engine 强大（JE3HHT） | 停更多年 | 引擎协议参考（独立实现） |
| RX-SSTV | freeware | 用 MMSSTV Engine 后端、维护活跃、自动模式检测+DSP | 闭源 | 功能参考 |
| QSSTV | GPL | Linux 原生、三窗口、兼容 MMSSTV/EasyPal | Qt 重 | **GPL 可拿**，解码核心参考 |
| Robot36 | 免费（安卓） | 处理 slant 好 | 手机向 | 参考 |
| EasyPal/DigTRX | 免费 | 数字 SSTV（DRM 开放标准） | 小众 | 后置 |

### 3. 数字模式（FT8/弱信号）

| 软件 | 许可 | 优点 | 结论 |
|---|---|---|---|
| WSJT-X | GPL-3.0 | FT8/FT4/Q65/MSK144/WSPR 全协议，QEX 论文公开 | **AGPL 可吞**；核心用 Fortran 复杂，务实路径：参考 QEX 协议文档独立实现解码器 |
| JS8Call | GPL-3.0 | FT8 变体自由文本 | 后置，消息协议参考 |
| Fldigi | GPL-3.0 | CW/PSK/RTTY/Olivia 调制解调 | 已有 psk31.py，可参考补 RTTY |

### 4. SDR 软件

| 软件 | 许可 | 优点 | 结论 |
|---|---|---|---|
| SDR# | 免费（部分闭源） | 生态插件最多 | UI 参考 |
| SDR++ | GPL-3.0 | 跨平台现代、瀑布图流畅 | **可拿** UI/FFT 思路 |
| GQRX | GPL-3.0 | Linux 原生 | 可参考 |
| SatDump | GPL-3.0 | APT/LRPT/GOES 解码链完整 | **可拿**解码链架构 |

### 5. APRS

| 软件 | 许可 | 优点 | 结论 |
|---|---|---|---|
| Direwolf | GPL-2.0 | 软件 TNC 成熟 | 已有 aprs.py 独立实现，igate 逻辑参考 |
| APRSIS32 | 免费 | 地图客户端 | UI 参考 |

## 二、集成架构（独立组件 + 总线）

```
┌─ radio_suite（独立组件，不塞进 lumo 壳）───────────────┐
│                                                       │
│  解码层 rf_brain（统一入口 decoders/registry.py）       │
│   ├─ ft8/wspr 解码器（新，Y-02）                       │
│   ├─ sstv 解码器（新，Y-03）                           │
│   ├─ aprs.py（已有）→ igate 扩展（Y-06）               │
│   ├─ 卫星 APT 解码（新，Y-05）                         │
│   └─ ook/ acurite lacrosse（已有，哨兵）               │
│                                                       │
│  控制层 rsba1_adapter（705，已有 8 工具）               │
│  日志层 hamlog 升级（Y-01）                            │
│  前端 radio UI（独立 Web/窗口，Y-04 频谱面板）           │
└───────────────┬───────────────────────────────────────┘
                │ 总线（ZMQ/MQTT + mcpserver 工具注册）
┌───────────────▼───────────────────────────────────────┐
│ 消费者（解耦，不互相依赖）                              │
│  ├─ 陆墨/Hermes：通过 mcpserver 工具调用（"解码这信号"） │
│  ├─ 事件订阅：解码结果/通联事件/频谱数据推送             │
│  └─ 冥王峡谷：哨兵/igate/wspr 数据交换                  │
└───────────────────────────────────────────────────────┘
```

**总线约定**：
- **控制/查询**：mcpserver 工具注册（agent-manifest.json，陆墨/林楠直接调用）
- **事件流**：ZMQ（复用 fusion_bus 模式 PUB/SUB）或 MQTT——信号到达、解码完成、QSO 记录、频谱帧
- **数据**：SQLite（日志/频谱元数据）+ 文件（IQ/音频/图像）
- **前端**：radio_suite 自带独立 UI（Web 面板），不并入 lumo 聊天界面；需要时事件推送给任意端

## 三、模块设计

### Y-01: 日志升级（hamlog 短板补齐）
- **问题**：无 ADIF 导入/导出、无 DXCC 追踪、无 CAT 联动、无统计
- **参考**：Log4OM 功能集（DXCC 追踪/集群）、Cloudlog 展示层思路
- **动作**：hamlog_adapter 扩展——ADIF 导入/导出、DXCC 实体追踪（奖状进度）、统计（月份/模式/波段）、CAT 联动（rsba1_adapter 通联自动填日志）；radio UI 日志视图（独立面板）
- **验收**：ADIF 导出文件可被其他日志软件导入；DXCC 进度视图；705 通联一键入日志（复用 X-01 联动）

### Y-02: FT8/WSPR 解码器（rf_brain）
- **参考**：QEX 论文《The FT4 and FT8 Communication Protocols》（公开协议文档）+ WSJT-X（GPL-3.0，AGPL 兼容，算法参考）
- **动作**：decoders/ft8.py（15s 帧、74-bit 消息、LDPC FEC、同步检测）+ wspr.py（2min 帧、弱信号）；注册进 registry；输入为 IQ/音频样本，输出结构化通联 JSON
- **验收**：合成/公开样例信号解码出正确呼号/网格；注册表可见；测试 ≥8

### Y-03: SSTV 解码器（rf_brain）
- **参考**：SSTV 公开协议（Martin M1/M2、Robot 36/72、SCT 模式表）+ QSSTV（GPL 可拿）
- **动作**：decoders/sstv.py（VIS 识别 → 同步/行扫描 → 模式解码 → PIL 图像输出）；音频输入，输出 PNG
- **验收**：公开样例 SSTV 音频解码出图像；VIS 自动识别；测试 ≥6

### Y-04: SDR 频谱面板（radio UI 独立面板）
- **参考**：SDR++/GQRX 瀑布图 UI 思路（GPL 可拿 UI 逻辑）
- **动作**：频谱数据源（RTL-SDR 直连或 rf_brain 采集）→ FFT 处理 → 前端瀑布图 + 频谱视图；频率点击联动 rsba1_adapter（调 705）
- **验收**：RTL-SDR 插入显示实时频谱；瀑布图滚动；点击频率联动 705（mock 或真机）

### Y-05: 卫星 APT 解码（rf_brain satellite）
- **参考**：SatDump 解码链架构（GPL-3.0 可拿）
- **动作**：satellite/apt.py（NOAA APT 137MHz：帧同步 → 去斜 → 图像合成）；配合 RTL-SDR + V-dipole
- **验收**：公开 APT 样例数据解码出 NOAA 云图；测试 ≥4

### Y-06: APRS igate 扩展（rf_brain）
- **参考**：Direwolf igate 逻辑（GPL-2.0 可拿）
- **动作**：aprs.py 已有解码 → 扩展 igate（解码的 APRS 包上报到 aprs.fi/本地地图）；冥王峡谷 direwolf 对照验证
- **验收**：解码 APRS 包 → igate 上报链路（mock 服务器可测）；本地地图可见

## 四、许可纪律（用户已拍板 2026-08-25）

- **本项目 AGPL-3.0，可吞 GPL-2.0/GPL-3.0 代码**（AGPL 是 GPL 超集，兼容）
- 拿代码路径：直接融合（GPL 系）或独立实现（freeware/闭源只参考协议与功能，如 MMSSTV Engine）
- 每个模块文件头标注来源与许可（授粉报告格式，照 FUSION-LOG 惯例）
- freeware（MMSSTV/RX-SSTV）不 copy 代码，只参考协议文档与功能清单

## 五、实施顺序

Y-02（FT8/WSPR，最贴 BG5GXO）→ Y-01（日志，用户反馈问题）→ Y-04（频谱面板，可视化底座）→ Y-03（SSTV）→ Y-05（卫星）→ Y-06（igate）。

## 六、提交规范

- 本 SPEC 进 scratchpad 仓库（工单分支）；施工走 trae/agent-y 分支（天选7 Trae）
- rf_brain 侧模块云服可直接写（纯 Python）；前端/705 联动天选7 验证
- 真机验证点（705 真机/RTLSDR/天线）统一列明，留用户实测
- 发现假设不成立 → 回填本 SPEC

---

*制定：沈遥（Hermes）· 2026-08-25*
*依据：SPEC-Writing-Standard-v2 + 同类软件对比调研 + 用户 8-25 拍板（混合集成/GPL 松绑）*
