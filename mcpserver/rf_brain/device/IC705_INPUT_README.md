# IC-705 / SDR 输入抽象 · 接口文档

> 来源：`mcpserver/rf_brain/device/`（Phase 7 交付，provider 注册表模式）
> 真机对接查阅版：本文档由 `device/base.py` 接口 docstring 整理导出，二者内容一致，以代码为准。
> 关联：SPEC-01 rf_brain 全自动闭环 Phase 7（任务 7.1 输入适配 / 任务 7.2 真机闭环）

---

## 1. 背景与目标

Phase 1-6 的输入是 numpy 仿真复数 IQ（`sensor.generate_iq`）。真机阶段，
**IC-705 通过 USB 以 USB Audio Class 枚举成系统"声卡"**，输出的是**解调后的
实音频流**（基带实信号，48 kHz 单声道典型）。

本抽象把"实音频帧"统一成 `AudioSource.read() → AudioFrame`，主流程只消费
这个形态，不感知后端（USB 声卡 / WAV 文件 / numpy 仿真）。

```
采集后端(USB声卡/WAV/仿真) → AudioSource.read() → AudioFrame
    → frame.to_iq()（Hilbert 实→复基带）→ decoders.decode_all(iq, sr)
```

## 2. 包结构

```
device/
├── base.py              # AudioFrame / AudioSource / iq_from_audio（接口本体）
├── registry.py          # register_source / create_source / list_sources
├── ic705.py             # Ic705UsbAudioSource —— IC-705 USB 声卡后端
├── wavfile.py           # WavFileSource —— WAV 离线回放（标准库 wave，零依赖）
└── sim.py               # SimulatedSource —— numpy 仿真注入（默认 DTMF 拨号）
```

注册表与解码器注册表同构：新增后端 = 新模块（继承 `AudioSource`）+ 一行
`@register_source` 装饰器，主流程零改动。

## 3. API 速查

### 3.1 数据载体 `AudioFrame`

```python
@dataclass(frozen=True)
class AudioFrame:
    samples: np.ndarray                # 1D float 实音频（-1.0 ~ 1.0）
    sample_rate: float                 # 采样率 Hz（IC-705 典型 48000）
    center_freq_hz: float | None = None  # 射频中心频率（IC-705 当前 VFO）
    meta: dict[str, Any] = ...         # 附加元数据（时间戳/模式/源名）

    def to_iq(self) -> np.ndarray:     # 实音频 → 复基带 IQ（Hilbert）
    def info(self) -> dict:            # 帧摘要（日志/调试）
```

### 3.2 输入源抽象 `AudioSource`（ABC）

所有后端实现同一协议：

```python
class AudioSource(ABC):
    name: ClassVar[str]        # 注册名（工厂键）
    description: ClassVar[str]

    def open(self) -> None                 # 打开后端；失败抛 RuntimeError
    def close(self) -> None                # 释放资源；幂等
    def read(self, max_samples=None) -> AudioFrame  # EOF 抛 StopIteration
    def info(self) -> dict                 # 后端静态信息
    # 支持 with 语句（__enter__ 自动 open / __exit__ 自动 close）
```

### 3.3 注册表与工厂（`device/registry.py`）

```python
register_source(cls)        # 类装饰器：按 cls.name 注册
list_sources() -> list[str] # ['ic705', 'wav', 'sim']
create_source(kind, **kwargs) -> AudioSource  # 工厂；未知名抛 KeyError
```

### 3.4 实音频 → 复基带（`device/base.iq_from_audio`）

```python
iq_from_audio(x: np.ndarray, sample_rate: float) -> np.ndarray
```

analytic signal（Hilbert 单边带）：正频分量加倍、负频清零，把实谱折叠成
复基带 IQ。实部 = 原信号，虚部 = Hilbert 变换。AFSK/BPSK 相位解调必需；
DTMF/POCSAG 等仅需幅度的协议对 IQ 同样适用（解码器内部取实部）。

## 4. 后端明细

### 4.1 `Ic705UsbAudioSource`（真机主后端，`device/ic705.py`）

```python
create_source("ic705",
    capture_fn=None,          # 采集回调 () -> 1D float 声卡样本（推荐）
    sample_rate=48000.0,      # IC-705 USB 声卡典型采样率
    center_freq_hz=None,      # IC-705 当前 VFO；非 None 构造即过白名单
    device_index=None,        # pyaudio 输入设备索引（可选）
    chunk=4096)               # 单帧最大样本数
```

- **依赖无关**：顶层不 import 任何音频库。真实采集后端经 `capture_fn` 回调注入
  （底层用 pyaudio / sounddevice / 系统命令皆可，本类不感知）；未提供回调时
  懒加载 pyaudio 读默认输入设备，未安装抛人类可读 `RuntimeError`（绝不静默）。
- **白名单强制**：`center_freq_hz` 非 None 时构造即过
  `amateur_bands.assert_allowed_freq`（业余频段，与 rsba1_adapter 同闸门）。

### 4.2 `WavFileSource`（离线回放/测试，`device/wavfile.py`）

```python
create_source("wav", path=..., center_freq_hz=None)
```

标准库 wave，零依赖，16-bit PCM（单/双声道，立体声取左声道）。

### 4.3 `SimulatedSource`（仿真注入，`device/sim.py`）

```python
create_source("sim", gen_fn=None, sample_rate=8000.0, duration_s=2.0,
              center_freq_hz=None, seed=1, digits="12345", snr_db=20.0)
```

默认合成 DTMF 拨号串（`decoders/dtmf.encode_dtmf`），可注入自定义
`gen_fn(sample_rate, n) -> 1D float ndarray` 合成 APRS/PSK31/POCSAG 音频帧。

## 5. 真机接入步骤（任务 7.2 闭环）

前置：IC-705 经 USB 连接，系统识别出声卡设备；rsba1_adapter（CI-V 控制桥）
可用（设频/读频）。

```python
import numpy as np
from mcpserver.rf_brain import device, decoders
# rsba1_adapter 实际包路径（注意不是 rf_brain 子包）：
from mcpserver.adapters.rsba1_adapter.adapter import Rsba1Ic705Bridge

# 1) 建立 CI-V 控制桥并设 VFO（RadioLink 直连优先，RemoteUty 兜底；
#    白名单已在 ic705_set_freq 内部强制）
bridge = Rsba1Ic705Bridge()
bridge.ensure()                                  # 失败抛人类可读 RuntimeError
bridge._tools()["ic705_set_freq"](145.8)         # 设 2m VFO（单位 MHz）
# 规范入口是 bridge.handle_handoff(task)（MCP unified_call），工具分发表 _tools()
# 仅供脚本化直用：{"ic705_set_freq", "ic705_read_freq", "ic705_ptt", ...}

# 2) 读解调音频（capture_fn 由你的音频后端实现，例如 pyaudio/sounddevice）
def capture():
    # ... 读一段声卡样本，返回 1D float ndarray
    ...

with device.create_source("ic705", capture_fn=capture,
                          sample_rate=48000.0, center_freq_hz=145_800_000) as src:
    frame = src.read()

# 3) 全协议解码（注册表泛型遍历，无协议分支）
iq = frame.to_iq()
for r in decoders.decode_all(iq, frame.sample_rate):
    if r.success:
        print(f"[{r.decoder}] {r.message}")
```

## 6. 设计约束（勿破坏）

1. **依赖无关**：`device/` 顶层禁止 import pyaudio / sounddevice / soundcard。
   无音频库时包仍可导入，WAV / 仿真离线链路照常工作。
2. **频段白名单**：任何携带射频频率的源必须过 `amateur_bands.assert_allowed_freq`
   （与 rsba1_adapter → civ_commands 同一道闸门，数值一致副本在 `amateur_bands.py`）。
3. **主流程零分支**：只消费 `create_source(kind, **kw)`，禁止硬编码后端分支。

## 7. 测试与验收（test_phase7.py，29 项）

- 注册表：ic705/wav/sim 三后端注册 + 工厂构造 + 未知名拒绝 + ABC 不可实例化
- WAV 回放：读回正确、EOF StopIteration、越界频率构造拒绝、max_samples 单帧不超限
- `iq_from_audio`：+1000 Hz 单边带保留 / -1000 Hz 清零 / 实部 = 原信号
- IC-705：白名单放行/拒绝、capture_fn 回调驱动 read、max_samples 截断、
  无 pyaudio 时 open 抛可读错误、拦截导入失败包仍可用
- 契约回归（铁锚审查补 8 项）：sim 越界频率拒绝、wav/sim `max_samples` 截断、
  `duration_s` 生效、capture_fn/gen_fn 空帧与 NaN 抛 RuntimeError、gen_fn 收到
  请求样本数
- 全链路闭环：sim 与 WAV 音频 → to_iq → `decode_all` 解出 DTMF（真机链路替身）
- 白名单对齐哨兵：`AMATEUR_BANDS` 数值 == rsba1_adapter（civ_commands）

## 8. 已知限制

- **DTMF 相邻重复键合并**（`"88"→"8"`）：仿真编码器 20 ms 静音间隔 + 解码器
  512 样本滑动帧的固有特性；真机 ITU 标准间隔 40-80 ms 不受影响。
- **IC-705 真机采集未验证**：属任务 7.2 用户配合项，需真机 USB 枚举 + 本机
  音频后端（`capture_fn` 回调或安装 pyaudio）。
