# GridSetup 分析报告

> 工单 3 交付物 | 分析对象：`rounakagrawal7/GridSetup`（GRID v2）
> 分析方法：`git clone --depth 1` 到本地，通读 `grid_radio.py` / `grid_satellite.py` 及依赖清单
> 结论速览：**GRID 的 radio/satellite 层是"纯网络数据聚合"，与 IC-705 硬件控制零耦合**，SDR 仅做 RTL-SDR 本地调谐听音，不能替代 Mailslot→RemoteUtility 控制路径

---

## 一、SDR / 无线电集成

### 1.1 硬件支持

| 层级 | 硬件 | 用途 | 触发方式 |
|------|------|------|---------|
| Tier 1 | 无硬件（纯网络） | Radio-Browser.info 全球广播电台目录 | `radio browser ...` |
| Tier 2 | 无本地硬件（网络远端） | KiwiSDR 全球公共接收机网络 | `radio kiwi ...` |
| Tier 3 | **RTL-SDR USB 棒（可选）** | 本地调谐 + FM 解调 + 频谱扫描 | `radio rtl ...` |

**明确不支持**：ICOM IC-705、任何 CI-V 设备、任何本地收发信机。GRID 的 radio 层**只做"收听/浏览"，不做"发射/控制"**。

### 1.2 驱动 / 库

| 组件 | 库 | 许可 | 说明 |
|------|-----|------|------|
| RTL-SDR | `pyrtlsdr` | GPL-2.0（运行时依赖，懒加载自动安装） | 仅在 `radio rtl` 被调用时 `_ensure_dep("pyrtlsdr")` 安装 |
| KiwiSDR 音频 | `websocket-client` | Apache-2.0（懒加载） | `radio kiwi stream` 时安装 |
| FM 解调 | `numpy`（`np.diff/np.unwrap/np.angle`） | BSD-3 | 直接内联，无独立 DSP 库 |
| Radio-Browser | `urllib` 标准库 | 无 | HTTP JSON API |
| **依赖安装机制** | `subprocess pip install`（grid_radio.py L31-46） | — | ⚠️ 见"安全注意" |

### 1.3 数据流架构

```
radio browser ──▶ Radio-Browser.info API (de1/at1/nl1 主备轮询) ──▶ 站名/流派/流URL
radio kiwi    ──▶ kiwisdr.com/public 目录(HTML解析) / JS fallback ──▶ 全球接收机清单
radio kiwi stream ──▶ ws://host:8073/ws WebSocket ──▶ 8000Hz 单声道 → 手写 WAV 头
radio rtl tune ──▶ pyrtlsdr → RtlSdr → center_freq/sample_rate → numpy FM解调 → .wav
radio rtl scan ──▶ 逐频点 power 测量 → ASCII 频谱条
```

**频率范围**：
- KiwiSDR：10kHz – 30MHz（短波 + LF/MF）
- RTL-SDR：24MHz – 1.7GHz（受 dongle 能力限制，FM 广播为主）
- Radio-Browser：流媒体目录（不限波段）

## 二、卫星追踪

### 2.1 数据源（均为免费、无 API key）

| 数据源 | URL | 提供内容 | 更新频率 |
|--------|-----|---------|---------|
| **Celestrak** | `celestrak.org/NORAD/elements/gp.php` | TLE 轨道根数（`?CATNR=<id>&FORMAT=TLE`） | 随 NORAD 两行根数更新 |
| **wheretheiss.at** | `api.wheretheiss.at/v1/satellites/<id>` | 实时经纬度/高度/速度/轨道特征 | 实时 |
| **Open Notify** | `api.open-notify.org` | ISS 位置 + 在轨宇航员名单 | 实时 |

### 2.2 数据格式
- **TLE**：标准两行根数（NORAD 格式），模块内联解析 inclination/RAAN/ecc/mean motion 等
- **wheretheiss.at**：JSON（latitude/longitude/altitude/velocity/perigee/apogee/inclination/period）
- **Open Notify**：JSON（`astros.json` 宇航员名单 + `iss-now.json` 坐标）

### 2.3 内置目录
`POPULAR_SATS` 硬编码约 50 颗卫星（ISS/Hubble/NOAA/GOES/GPS/Galileo/Starlink/天宫），`SAT_GROUPS` 按用途分组（weather/gps/starlink/amateur 等）。

## 三、与 N.E.K.O. radio 层嫁接可行性

> N.E.K.O./陆墨 当前 IC-705 控制路径：Mailslot `RemoteUtyCtrlCmd` → RemoteUtility → 电台（CI-V），见 rs-ba1-reverse。

### 3.1 可直接复用（低风险，建议）

| 组件 | 复用价值 |
|------|---------|
| **卫星追踪（grid_satellite.py）** | 完整、无 key、纯标准库。与 IC-705 无冲突，可独立作为陆墨的"太空/短波信号追踪"知识源。APRS 卫星、NOAA 气象卫星、业余无线电卫星(`amateur`组) 与 SDR 交叉栈天然契合 |
| **Radio-Browser 目录查询** | 全球广播站目录，作为"该频段有什么"的辅助信息 |
| **KiwiSDR 网络收听** | 陆墨可远程收听世界短波，辅助频率监测（只读，无硬件冲突） |

### 3.2 需适配（中风险）

| 组件 | 适配点 |
|------|--------|
| **RTL-SDR 调谐** | 若陆墨接入 RTL-SDR dongle 用于频谱监测，可复用 FM 解调/扫描逻辑；但 IC-705 与 RTL-SDR 是**两条独立硬件链**，不互相干扰，也不互相替代 |

### 3.3 不可用（不可替代 IC-705 控制）

| 组件 | 原因 |
|------|------|
| **IC-705 控制（GRID 无此能力）** | GRID radio 层**完全没有** CI-V / 收发信机控制协议。GRID 是"网络 SDR + RTL 收听"聚合器，**不发射、不控制、不与 IC-705 通信**。陆墨控制 IC-705 必须走既有 Mailslot→RemoteUtility 路径，**不能**用 GridSetup 替换 |

---

## 四、安全注意（供实验田维护者参考，非本工单施工项）

1. **自动 `pip install`（grid_radio.py L31-46）**：运行时代码在 ImportError 时自动 `subprocess.run([sys.executable, "-m", "pip", "install", pkg])`。虽参数化无注入，但**自动联网装包**在加固场景应禁用。
2. **懒加载依赖**：`pyrtlsdr`/`websocket-client` 仅调用时安装，未进 `requirements.txt` 主清单，部署环境需显式声明。
3. **频率无白名单**：`radio rtl tune <freq_mhz>` 接受任意频率（含非业余频段）。若嫁接到陆墨，频率设置仍需按项目硬约束走业余波段白名单（1.8-30 / 50-54 / 144-148MHz）。

---

## 五、总结

GRID 的 radio/satellite 层是**高质量的"网络 SDR 收听 + 卫星追踪"工具**，卫星模块尤其完整可直接复用。但它**不是**电台控制工具——与 IC-705 的 Mailslot/CI-V 控制路径零交集。陆墨控制 IC-705 不受 GRID 影响，GRID 可作为**辅助频谱情报/卫星追踪**层并入 SDR 交叉栈数据源清单。

*报告生成时间：2026-08-12 | 分析：Trae IDE（执行侧）*
