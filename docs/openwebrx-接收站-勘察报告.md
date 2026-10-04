# openwebrx Web SDR 接收站勘察报告 · 2026-08-23（工单 G-03）

**勘察源**: ha7ilm/openwebrx（AGPL-3.0，2024-06 归档）
**勘察方式**: clone /tmp，读多用户接收架构
**对照基线**: 用户接收站方案（IC-705 遥控 + rf_brain + ESP32/SDR 前哨）
**结论**: openwebrx 的多用户架构是「SDR 服务器 + Web 客户端」参考，但**直接部署不可行**（AGPL + Python2 + 2014 年代架构 + 依赖 csdr C 程序）；**组件提取**价值集中在「每客户端独立 DSP 管道」模式。

---

## 1. 架构图

```
SDR 硬件（rtl-sdr 等）
    ↓ USB
rtl_thread（采集线程）
    ↓ IQ 数据
┌─────────────────────────────────────────┐
│ MultiThreadHTTPServer（:8073）           │
│  ├── WebRXHandler.do_GET                 │
│  │    每客户端创建独立 dsp 实例           │
│  │    dsp.chain('nfm'/'am'/'ssb')        │
│  │    → csdr 管道进程链                   │
│  │      shift→decimate→bandpass→         │
│  │      squelch→demod→AGC→音频           │
│  ├── spectrum_thread_function            │
│  │    FFT → logpower → 压缩 → 推送        │
│  └── WebSocket (rxws)                    │
│       每客户端独立 WS 连接收音频/频谱      │
└─────────────────────────────────────────┘
```

**多用户隔离机制**：
- 每个客户端一个 `dsp` 实例 → 一条独立 csdr 管道链（`csdr.py:66 chain()`）
- 客户端间不共享 DSP 状态（各自 shift/decimate/demod 参数独立）
- 频谱线程全局一份广播，音频每客户端独立
- 客户端清理：`cleanup_clients` + 超时 watchdog

## 2. 关键设计拆解

### 2.1 csdr 管道链模式（最值钱）
`csdr.py:66 chain()` 把 DSP 组成 shell 管道：
```
nc (netcat 接 IQ) | csdr shift_addition_cc | csdr fir_decimate_cc |
csdr bandpass_fir_fft_cc | csdr squelch_and_smeter_cc | csdr fmdemod_quadri_cf |
csdr deemphasis_nfm_ff | csdr convert_f_s16 → WebSocket
```
**值钱点**：每个处理阶段是独立小进程，参数热改（--fifo 管道），崩溃隔离（一个 csdr 挂不影响其他）。这正是 rf_brain 需要的「模块化 DSP 链」——但 rf_brain 用 numpy 单进程即可，不必进程级隔离（开销大），**抄链式编排概念**（stage 列表 + 参数传递），不抄进程架构。

### 2.2 每客户端独立 dsp 实例
`openwebrx.py:110 main` 的 clients 字典 + `csdr.py:32 dsp.__init__`：每客户端独立实例化。**授粉**：rf_brain 的 receiver 场景（多用户监听不同频率）需要此模式——每个监听会话独立 demod 状态，共享 sensor 数据源。

### 2.3 频谱广播 vs 音频独立
频谱线程全局广播（`spectrum_thread_function`）+ 音频每客户端独立。**授粉**：rf_brain scanner 的频谱展示可全局一份，解调结果按订阅分发——避免重复 FFT。

## 3. 接入可行性结论

| 方案 | 可行性 | 理由 |
|------|--------|------|
| 直接部署 | ❌ 不可行 | Python2 + 2014 架构 + csdr C 依赖 + AGPL 全仓（与 AGPL 主仓同许可但架构太老） |
| 组件提取 | ⚠️ 部分可行 | 只提取「DSP 链式编排 + 每客户端独立实例」设计模式，Python/numpy 重写 |
| 仅参考 | ✅ 建议 | 多用户 Web SDR 的场景（手机浏览器听电台）与 IC-705 遥控方案重叠，先记设计后评估 |

## 4. 依赖清单（若部署需）

- csdr（C 程序，GitHub jopohl/csdr）——DSP 管道底层
- rtl-sdr / hackrf 驱动
- Python2.7（老版本）或移植到 Py3
- WebSocket 前端（htdocs 自带）

**结论**：openwebrx 的价值 = 「多用户 SDR 接收的架构样板」+「DSP 链式编排的模块化思想」。对用户当前方案（IC-705 遥控 + rf_brain 本地决策）而言，**架构参考级别**——rf_brain 的 scanner/loop 已覆盖单用户接收，多用户 Web 分发留待有部署场景时再评估（可考虑 sdrtrunk W-01 已勘察的兄弟方案）。

*—— 实验田维护者 · 接收站不急着盖楼，先想清楚几个房间——每间房独立听，但水管共用一根 🐾*
