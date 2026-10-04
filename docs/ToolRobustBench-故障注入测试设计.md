# ToolRobustBench · MCP/ hermes_proxy 总线故障注入测试设计

> 2026-08-29 · 实验田维护者线完成（原 AC-03/04 安全部分）· 论文：Sim-to-Real Benchmark 2605.11928（22 perturbation types，4 POMDP 组件）+ fault_inject 框架对标
> 用途：给 hermes_proxy / mcpserver 总线链路设计故障注入回归集，量化「断链不崩、限流不失活、降级可恢复」
> 现有基线：mcpserver/fault_inject/（E-01~E-02，7 故障类型 + RobustCaller + 预置场景 + MCP 桥 + 完整测试）

## 一、论文perturbation类型（22种，按POMDP组件分组）

来自 Sim-to-Real Benchmark（2605.11928）——RobustBench-TC，22 perturbation types：

| 组件 | perturbation类型 | 说明 |
|------|----------------|------|
| State | domain_randomize_sensor | 传感器域随机化 |
| State | occlusion | 视觉遮挡 |
| State | additive_noise | 加性噪声 |
| Observation | latency_jitter | 观测延迟抖动 |
| Observation | packet_drop | 数据包丢失 |
| Observation | sensor_bias | 传感器偏置 |
| Transition | dynamics_mismatch | 动力学失配 |
| Transition | friction_variance | 摩擦力变化 |
| Transition | action_delay | 动作延迟 |
| Reward | reward_noise | 奖励噪声 |
| Reward | reward_scale | 奖励缩放 |
| Reward | reward_delay | 奖励延迟 |
| Agent | tool_schema_corrupt | 工具schema损坏 |
| Agent | tool_param_noise | 工具参数噪声 |
| Agent | api_version_drift | API版本漂移 |
| Agent | auth_token_expire | 认证token过期 |
| Agent | rate_limit_hit | 限流命中 |
| Agent | mcp_server_crash | MCP服务器崩溃 |
| Agent | circular_dependency | 循环依赖 |
| Environment | network_partition | 网络分区 |
| Environment | resource_contention | 资源竞争 |
| Environment | clock_skew | 时钟偏移 |

## 二、现有框架覆盖度

现有 `fault_inject` 覆盖 7 种，对照上表：

| 论文perturbation | 现有FaultType | 覆盖状态 |
|-----------------|--------------|---------|
| rate_limit_hit | MCP_RATE_LIMIT | ✅ 已有 |
| mcp_server_crash | MCP_DISCONNECT | ✅ 已有（断连）|
| tool_schema_corrupt | TOOL_ERROR | ✅ 已有（工具异常）|
| api_version_drift | TOOL_ERROR | ✅ 已有 |
| auth_token_expire | MCP_DISCONNECT | ✅ 已有 |
| action_delay / latency_jitter | MCP_SLOW | ✅ 已有 |
| circular_dependency | MCP_DISCONNECT（嵌套）| ⚠️ 间接覆盖 |
| tool_param_noise | PREFIX_PERTURB | ✅ 已有 |
| network_partition | MCP_DISCONNECT | ✅ 已有 |
| clock_skew | （无独立类型）| ❌ 缺失 |
| resource_contention | （无独立类型）| ❌ 缺失 |
| packet_drop | MCP_DISCONNECT | ⚠️ 间接覆盖 |
| domain_randomize_sensor | （无独立类型）| ❌ 缺失 |
| reward_noise/scale/delay | （不在范围内）| ℹ️ 不适用（无reward概念）|

**Gap 清单（3个新增类型）：**
1. `clock_skew` — 时钟偏移导致消息序列号乱序/重复
2. `resource_contention` — 资源竞争导致响应时间尖峰（不等同于slow，需模拟CPU/内存压力）
3. `domain_randomize_sensor` — 传感器域随机化（对应工具返回字段随机缺失/类型漂移）

## 三、测试设计文档

### 3.1 新增故障类型（faults.py 扩展）

```python
# 新增 FaultType
CLOCK_SKEW = "clock_skew"          # 时钟偏移：序列号乱序/消息重复
RESOURCE_CONTENTION = "resource_contention"  # 资源竞争：响应时间尖峰
DOMAIN_RANDOMIZE_SENSOR = "domain_randomize_sensor"  # 传感器漂移：返回字段缺失/类型错误
```

### 3.2 回归测试矩阵（MCP总线 / hermes_proxy / mcpserver）

| 测试ID | 故障注入点 | perturbation类型 | 触发方式 | 期望行为 |
|--------|-----------|----------------|---------|---------|
| T-01 | hermes_proxy → mcpserver | rate_limit_hit | MCP_RATE_LIMIT persistent | 退避重试，指数回退，≤3次恢复 |
| T-02 | hermes_proxy → mcpserver | mcp_server_crash | MCP_DISCONNECT persistent | 重连回调触发，恢复后接续 |
| T-03 | hermes_proxy → mcpserver | auth_token_expire | MCP_DISCONNECT once | token刷新后重试，状态不丢失 |
| T-04 | hermes_proxy → mcpserver | action_delay | MCP_SLOW (delay=0.5s) | 超时阈值内返回，降级提示用户 |
| T-05 | hermes_proxy → mcpserver | tool_schema_corrupt | TOOL_ERROR persistent | 降级路径触发，返回友好错误 |
| T-06 | hermes_proxy → mcpserver | tool_param_noise | PREFIX_PERTURB persistent | 路由字段不动，message字段扰动被过滤 |
| T-07 | hermes_proxy → mcpserver | circular_dependency | 嵌套MCP_DISCONNECT once | 超时保护触发，不死锁 |
| T-08 | hermes_proxy → mcpserver | network_partition | MCP_DISCONNECT persistent | 离线模式降级，有感知可恢复 |
| T-09 | hermes_proxy → mcpserver | clock_skew | CLOCK_SKEW persistent | 序列号校验失败报警，不崩 |
| T-10 | hermes_proxy → mcpserver | resource_contention | RESOURCE_CONTENTION persistent | 限流保护触发，队列不堆积 |
| T-11 | hermes_proxy → mcpserver | domain_randomize_sensor | DOMAIN_RANDOMIZE_SENSOR once | 字段校验失败报警，降级返回 |
| T-12 | mcpserver 内部 | mcp_server_crash | MCP_DISCONNECT persistent | 子agent崩溃不影响其他agent |
| T-13 | mcpserver 内部 | rate_limit_hit | MCP_RATE_LIMIT persistent | 单agent限流不影响全局调度 |
| T-14 | 综合 | combined（渐进恶化） | progressive 场景 | 逐级降级，用户无感知 |

### 3.3 量化指标（robustness.py CallOutcome 扩展）

每轮测试输出：
- `success_rate`：成功率（被测链路在故障下仍正确完成比例）
- `avg_retries`：平均重试次数
- `avg_recovery_s`：平均恢复时间（秒）
- `degraded_rate`：触发降级比例
- `reconnect_count`：重连次数
- `error_type`：触发的故障类型分布

### 3.4 集成方式（hermes_proxy / mcpserver 总线）

```python
# hermes_proxy 链路级注入（示例）
from mcpserver.fault_inject import FaultInjector, FaultSpec, FaultType, FaultMode

injector = FaultInjector()
injector.add_fault(FaultSpec(
    type=FaultType.MCP_RATE_LIMIT,
    mode=FaultMode.PERSISTENT,
    delay=0.1,
))
wrapped = injector.inject(hermes_proxy.mcp_call)
# 跑 T-01
```

### 3.5 触发方式（fault_inject 已支持，无需新写）

现有框架支持：
- ✅ `inject(func)` — 包裹单个函数
- ✅ `wrap_agent(agent)` — 包裹 agent 实例
- ✅ `install(obj, method_name)` — monkeypatch 总线方法
- ✅ `scenario.py` 预置场景 — combined / progressive 直接用

## 四、落地优先级

| 优先级 | 内容 | 工作量 |
|--------|------|--------|
| P0 | 运行现有 `run_robustness_suite(trials=20)` 获取基线指标 | 5分钟 |
| P0 | 新增 CLOCK_SKEW / RESOURCE_CONTENTION / DOMAIN_RANDOMIZE_SENSOR 三种类型 | ~50行 |
| P1 | T-01~T-08 写入 `tests/test_mcp_robustness.py`，纳入 CI | ~150行 |
| P1 | 补充 scenario.py 预置 clock_skew / resource_contention 场景 | ~20行 |
| P2 | T-09~T-14 补充完整回归矩阵 | ~120行 |

## 五、参考论文

- Sim-to-Real Benchmark（arXiv 2605.11928）：RobustBench-TC，22 perturbation types，SHIELD 基线防御把攻击成功率 69.5%→4%
- 与现有 fault_inject 互补：论文提供 perturbation 分类学，现有框架提供注入执行与量化 harness
