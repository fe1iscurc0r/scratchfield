# MODEL_INTERFACE: hololinked

- 上游仓库: https://github.com/hololinked-dev/hololinked
- 许可证: BSD-3-Clause（上游仓库；引用须保留，见 ../LICENSES.md）
- 安装: `pip install hololinked`（或 conda-forge）
- Python 模块名: `hololinked`

## 算法定位

Pythonic 面向对象仪器控制 / SCADA / IoT 框架：把硬件抽象为 Thing
（属性 Property + 动作 Action + 事件 Event），通过 HTTP / MQTT / ZMQ
暴露，兼容 W3C Web of Things（自动生成 Thing Description）。

## 核心 API

```python
from hololinked.core import Thing, Property, action, Event
from hololinked.core.properties import String, Number, List

class MyInstrument(Thing):
    integration_time = Number(default=1000, bounds=(0.001, None))

    @action()
    def connect(self): ...

    measurement_event = Event(name='measurement')

MyInstrument(id='dev').run_with_http_server(port=9000)   # HTTP 服务
# 或 run(access_points=['IPC', 'tcp://*:9999'])           # ZMQ

# 客户端
from hololinked.client import ClientFactory
thing = ClientFactory.http(url="http://host:9000/dev/resources/wot-td")
thing.read_property("integration_time")
thing.invoke_action("connect")
thing.subscribe_event("measurement", callbacks=cb)
```

## 数据格式

- 输入: Python 类定义（Property 带 schema 校验）；客户端走 WoT TD (JSON)
- 输出: JSON over HTTP / MQTT / ZMQ；事件支持 SSE 推送流式数据
- 附加: 状态机、SQLAlchemy 属性持久化、自动 TD 生成

## Lumo 工作台用途

- 实验仪器远程化/网络化封装（配合 WaveBench 的测量台）
- 多机分布式实验数据汇聚到中央存储

## 引用

hololinked-dev. hololinked: Pythonic Object-Oriented SCADA/IoT.
Zenodo DOI: 10.5281/zenodo.12802841. BSD-3-Clause.
