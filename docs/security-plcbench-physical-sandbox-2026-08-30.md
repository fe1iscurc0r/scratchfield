# S02 PLCBench 物理域 Agent 安全沙箱（ESP32+LoRa+SDR）

> 任务：S02 PLCBench 物理域 Agent 沙箱
> 来源：digest-g3-2-2026-08-30.md · 授粉点 1 · 核心论文 2608.26882《PLCBench》
> 日期：2026-08-30

---

## 一、问题陈述

PLCBench（2608.26882）证明：**LLM Agent 可以把"网络可达的 PLC"转为持续物理破坏**。对 ESP32+LoRa+SDR 节点，同样的威胁存在——Agent 一旦获得对物理接口的任意操作权，就可能通过无线通道注入恶意指令，造成物理后果。因此必须设计**物理域安全沙箱**：约束 Agent **只能通过预定义的 RF/物理接口**操作硬件，其余一律拦截。

## 二、沙箱边界设计

### 2.1 能力白名单（typed 接口）
- Agent 只暴露一组**预定义、带类型的能力接口**：`rf_transmit(freq, power, payload)`、`rf_receive(freq)`、`gpio_write(pin, val)` 等。
- 每个接口声明**合法参数域**（频率范围、功率上限、引脚集合）。
- 沙箱只放行这些接口的调用，任何"直接写寄存器 / 任意内存访问 / 未定义协议"的调用一律拦截。

### 2.2 参数域校验
- 频率/功率/占空比等参数必须落在合法域内（防止越权发射、超功率干扰）。
- 物理量级校验：发射时长上限、占空比上限，防止持续占用信道。

### 2.3 无线注入防护
- 从 LoRa/无线通道进来的指令，必须先经过**来源认证 + 完整性校验**才进入能力接口。
- 未认证/被篡改的无线指令直接丢弃，不进入 Agent 执行链。

## 三、原型骨架

```python
CAPABILITIES = {
    "rf_transmit": {"freq": (2400e6, 2483e6), "power": (0, 20)},
    "rf_receive":  {"freq": (2400e6, 2483e6)},
    "gpio_write":  {"pins": {1, 2, 3, 4}},
}

def sandbox_dispatch(action):
    cap = CAPABILITIES.get(action.name)
    if cap is None:
        return "reject:unknown_interface"        # 未定义接口 → 拦截
    if not within_domain(cap, action.args):
        return "reject:out_of_domain"            # 参数越域 → 拦截
    if action.origin == "wireless" and not authenticated(action):
        return "reject:unauthenticated"          # 无线注入未认证 → 拦截
    return execute(action)
```

## 四、拦截测试

| 恶意指令 | 沙箱拦截 |
|---|---|
| 直接写寄存器 / 任意内存 | reject:unknown_interface |
| 超功率 / 超频段发射 | reject:out_of_domain |
| 经 LoRa 注入的未认证指令 | reject:unauthenticated |
| 未定义的物理操作 | reject:unknown_interface |

**验收目标**：所有绕过预定义 RF/物理接口的恶意操作 100% 拦截。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| 沙箱边界文档 | §二（能力白名单 + 参数域 + 无线注入防护） |
| 原型 | §三 `sandbox_dispatch` 骨架 |
| 拦截测试 | §四 |
| 文档 | `docs/security-plcbench-physical-sandbox-2026-08-30.md` |
