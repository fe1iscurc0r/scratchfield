# Lumo EventBus v2 — 热插拔重构 SPEC

> 触发：lumo_event.py 硬编码 `from .lumo_state` 导致每加消费者都要改核心。
> 目标：消费者热插拔，核心零修改。

---

## 一、背景

### 现状（痛点）

```
lumo_event.py（事件入口）
  → 硬编码 import lumo_state   # 耦合点A
  → 硬编码 import lumo_proactive  # 耦合点B
  → 未来每加一个消费者，都要改这里
```

**反模式**：N 个消费者 = N 条硬编码接线。已踩 v1 总线规范的预警（EDA 反模式 #5 点对点耦合）。

### 参考来源

| 来源 | 抄什么 |
|---|---|
| Cordis (DeepSeek Harness vendor) | `effect` 可逆注册 + 五种 dispatch 模式 + 两段式发布 |
| caura-memclaw (vendor/) | Event 信封 + Topics 命名规范 |

**不抄**：fiber 树、Context 代理、依赖注入——Cordis 为"一切皆插件"付出的复杂度，陆墨单体 FastAPI 不需要。

---

## 二、接口契约（三条，不能动）

### 契约 A：`Disposable`

```python
# 所有注册返回精确 disposer，调用即卸载，不抛
type Disposable = Callable[[], None]
```

**约束**：
- 同一个资源调用两次 disposer = 第二次是 no-op
- disposer 是同步的（不等 async）

### 契约 B：`EventBus` 接口

```python
from abc import ABC, abstractmethod
from typing import Callable, Any

type Disposable = Callable[[], None]
# 标准 Topic handler：收到事件对象
type EventHandler[T] = Callable[[T], Any]
# Waterfall handler：收到 (事件对象, next函数)，调 next() 继续，不调则 veto
type WaterfallHandler = Callable[[object, Callable[[], Any]], Any]

class EventBus(ABC):
    @abstractmethod
    def on(self, topic: str, handler: EventHandler, *, prepend: bool = False) -> Disposable:
        """可逆注册。返回 disposer，调用后该 handler 从总线消失。"""

    @abstractmethod
    def emit(self, topic: str, event: object) -> None:
        """同步分发。所有 handler 无等待并行执行。"""

    @abstractmethod
    async def parallel(self, topic: str, event: object) -> None:
        """并发 await 所有 handler，全部完成后才返回。有任一 reject 则抛。"""

    @abstractmethod
    async def serial(self, topic: str, event: object) -> Any:
        """顺序 await，直到一个返回 bail 值（value is not None and value is not False）。"""

    @abstractmethod
    def bail(self, topic: str, event: object) -> Any:
        """同步 bail。顺序执行 handler，第一个非 None/False 返回值停止。"""

    @abstractmethod
    def waterfall(
        self,
        topic: str,
        event: object,
        final: Callable[[], Any] | None = None,
    ) -> Any:
        """
        洋葱链。每个 WaterfallHandler(event, next)：
          - 调 next() = 继续传播到下一个 handler 或 final
          - 不调 = veto，链的返回值即为此 handler 的返回值
          - 所有 handler 都不调 next = final 被调用
        用于：拦截、审批、熔断。
        """
```

### 契约 C：Topics 命名规范

```python
class Topics(str, Enum):
    # 事实（past-participle，已发生）
    USER_INPUT_RECEIVED  = "lumo.user.input.received"
    ASR_RESULT           = "lumo.asr.result"
    TTS_START            = "lumo.tts.start"
    TTS_END              = "lumo.tts.end"
    MEMORY_CREATED       = "lumo.memory.created"
    MEMORY_ARCHIVED      = "lumo.memory.archived"
    DECISION_COMPLETED   = "lumo.decision.completed"

    # 命令（requested，请求干活）
    SPEAK_REQUESTED      = "lumo.speak.requested"
    EMOTION_REQUESTED    = "lumo.emotion.requested"
    MEMORY_EMBED_REQUESTED = "lumo.memory.embed-requested"
    TOOL_PRE_EXECUTE     = "lumo.tool.pre-execute"    # waterfall 门

    # 内部
    INTERNAL_DISPATCH    = "internal/dispatch"         # 所有分发的预通知
    #   Payload: {"topic": str, "mode": str, "args": list}

    # 预留扩展（未来仪器/传感器接入）
    _RESERVED           = "lumo.reserved"
```

---

## 三、集成点（三处改动，均为加法，不动核心）

### 改动点 A：lumo_event.py

```python
# 原来
from .lumo_state import get_state_store
get_state_store().update(event)

# 改成
bus.emit(Topics.USER_INPUT_RECEIVED, event)
```

**约束**：lumo_event.py **只负责 emit**，不 import 任何消费者。

### 改动点 B：lumo_state.py

```python
# 原来（被动等调用）
get_state_store().update(event)

# 改成（主动订阅）
disposer = bus.on(Topics.USER_INPUT_RECEIVED, _handle_input)
```

### 改动点 C：lumo_proactive.py

```python
# 原来（主动订阅 + 自己起定时器）
from .lumo_state import get_state_store
state = get_state_store().read()

# 改成（订阅总线）
disposer = bus.on(Topics.USER_INPUT_RECEIVED, _handle_input)
# 定时器不改动——lumo_proactive 的定时器逻辑独立保留
```

### 改动点 D（可选，推荐）：安全门

```python
# lumo_proxy.py 工具调用前过 waterfall 门
result = bus.waterfall(
    Topics.TOOL_PRE_EXECUTE,
    {"tool": tool_name, "args": args},
    final=lambda: original_tool_call(tool_name, args),
)
```

---

## 四、实现要求

### 必须满足

1. `DisposableList` 逆序清理 + O(1) 按值删除（参考 utils.ts:5-40）
2. 五种 dispatch 全实现：`emit` / `parallel` / `serial` / `bail` / `waterfall`
3. `on()` 返回 `Disposable`，调用后 handler 永久消失
4. 所有消费者注册后，`lumo_event.py` **零修改**才能加新订阅者
5. 总线单例（整个进程只有一条总线，所有组件共享）

### 不要求

- 不要求多进程 / PubSub / 网络传输（等真需要再说）
- 不要求 fiber 树 / Context 代理 / 依赖注入容器
- 不要求完整的 Cordis 复刻

### 验收条件

```python
def test_disposer_once_only():
    bus = InProcessEventBus()
    count = 0
    def handler(_): nonlocal count; count += 1
    d = bus.on("test", handler)
    bus.emit("test", None)  # count=1
    d()
    bus.emit("test", None)  # count=1（handler 已卸载）
    d()  # 第二次 no-op，不抛
    bus.emit("test", None)  # count=1

def test_waterfall_veto():
    bus = InProcessEventBus()
    # WaterfallHandler(event, next) — 不调 next = veto
    bus.on("gate", lambda event, next: None)
    result = bus.waterfall("gate", {}, final=lambda: "fallback")
    assert result is None  # 被 veto，final 未运行

def test_consumer_plug_unplug():
    # lumo_event.py 不 import 任何消费者
    bus = InProcessEventBus()
    events = []
    bus.on(Topics.USER_INPUT_RECEIVED, lambda e: events.append(e))
    # 模拟 lumo_event.emit
    bus.emit(Topics.USER_INPUT_RECEIVED, {"type": "user_input"})
    assert len(events) == 1
    # 再加一个消费者，不改 lumo_event.py
    more = []
    bus.on(Topics.USER_INPUT_RECEIVED, lambda e: more.append(e))
    bus.emit(Topics.USER_INPUT_RECEIVED, {"type": "user_input"})
    assert len(events) == 2
    assert len(more) == 1
```

---

## 五、目录结构

```
apiserver/
  event_bus/
    __init__.py          # InProcessEventBus 单例导出
    bus.py               # EventBus ABC + InProcessEventBus 实现
    topics.py            # Topics StrEnum
    disposable.py        # DisposableList
    handlers.py          # 各消费者订阅逻辑（lumo_state / lumo_proactive）
    tests/
      __init__.py
      test_bus.py        # 三条验收条件
      test_waterfall.py  # waterfall veto 专项
      test_lifecycle.py  # 生命周期
```

---

## 六、已知消费者（截至 M3.1 落地）

| 消费者 | 订阅 Topic | 行为 |
|---|---|---|
| lumo_state | `USER_INPUT_RECEIVED` | 更新状态快照 |
| lumo_proactive | `USER_INPUT_RECEIVED` | 五门决策触发 |
| summer_memory | `MEMORY_CREATED`（新加） | 记忆生命周期 |

---

*基于 Cordis effect+events 原语调研（2026-08 DeepSeek Harness vendor/cordis）*
*整合 caura-memclaw Topics 命名规范（vendor/top5/caura-memclaw）*
