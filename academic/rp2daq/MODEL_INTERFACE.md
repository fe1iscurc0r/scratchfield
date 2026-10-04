# MODEL_INTERFACE: rp2daq

- 上游仓库: https://github.com/FilipDominec/rp2daq
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: 硬件固件（rp2daq.uf2 刷入 Raspberry Pi Pico）+ `pip install pyserial`；
  模块以源码目录方式引入（PYTHONPATH）
- Python 模块名: `rp2daq`（需连接硬件）

## 算法定位

Raspberry Pi Pico 数据采集与控制：预编译 C 固件 + 自动生成的 Python 接口。
模拟输入（12-bit，500k SPS）、步进电机（12 路）、数字 IO、PWM（16 路）。
固件与 Python 端通过启动时解析 C 代码自动生成命令，保证二进制兼容。

## 核心 API

```python
import rp2daq
rp = rp2daq.Rp2daq()               # USB 串口连接
rp.gpio_out(25, 1)                  # 点亮板载 LED
rv = rp.adc()                       # 默认 GPIO26 采 1000 点
rv.data                             # [0..4095] ↔ [0..3.2V]
rv = rp.adc(channel_mask=16)        # 内置温度传感器

# 异步模式（回调，不阻塞）
rp.adc(blocks_to_send=1000, _callback=my_callback)
# 步进电机: rp.stepper(...)，支持多电机异步编排
```

## 数据格式

- 输入: 命名参数（channel_mask, blocks_to_send, infinite 等）
- 输出: namedtuple 报告（data 列表 + 时间戳 + 同步值）
- ADC 标度: 0 ↔ 0 V，4095 ↔ ~3.2 V

## Lumo 工作台用途

- 低成本实验室数据采集（温度/湿度/简易传感器）接入
- 硬件在环时可用；无硬件时仅作接口文档储备

## 引用

Dominec, F. rp2daq: Raspberry Pi Pico for Data Acquisition. MIT License.
