# 案例报告：LoRaCanary 底板 v0.6 原理图程序化绘制

> 案例编号：CASE-26  
> 日期：2026-08-26  
> 涉及文件：`scripts/easyeda/draw_schematic.py`、`docs/SPEC-20-PCB前置资料-嘉立创AI.md`

---

## 1. 事件时间线

| 阶段 | 操作 | 结果 | 关键决策点 |
|------|------|------|------------|
| T0 | 用户授权开始绘制 LoRaCanary 底板原理图 | 任务启动 | 决定用 easyeda-agent 程序化绘制 |
| T1 | 读取 SPEC-20，整理网表和元器件表 | 得到 27 个器件的完整 netlist | — |
| T2 | 编写 `draw_schematic.py` 初版 | 使用 `eda.lib_Device.getByLcscIds()` + `eda.sch_PrimitiveComponent.create/modify/createNetFlag/createNetLabel` 的**整体式** JS，一次 `debug exec` 放置 27 个器件并打标号 | 采用了“一次画完”策略 |
| T3 | 第一次完整绘制 | `debug exec` 超时 120s，连接器开始降级 | 失败 |
| T4 | 改成 chunk_size=1（一次一个器件），但仍保留 `modify` 位号 | 前几个器件成功，但 `modify` 触发连接器进一步降级（35% → 45% 失败率） | 误判为“只是请求太大”，未意识到 `modify` 是敏感操作 |
| T5 | 多次重试后连接器完全卡死 | `debug exec` / `sch list` 均返回 `connector did not respond` | 应停止而未停止，持续重试加剧了降级 |
| T6 | 尝试 `daemon restart` | 心跳恢复，但 JS dispatch 仍超时 | 判断：阻塞发生在 EasyEDA Pro 扩展宿主内部，不是 daemon |
| T7 | 用户重启 EasyEDA Pro | 连接器恢复，`debug exec return 1+1` 成功 | 用户纠正了环境状态 |
| T8 | 重新运行初版脚本 | `getByLcscIds` 打开库浏览器，导致连接器再次在第一个器件放置时超时 | 未吸取教训，仍用 `getByLcscIds` |
| T9 | 发现 `easyeda lib search`（离线搜索）和 typed action `sch place` / `sch autoconnect` | `sch place` 放 J1 成功且稳定 | **关键转折点**：从 raw JS 转向 typed action |
| T10 | 重写 `draw_schematic.py`：离线 `lib search` + `sch place --designator` + `sch autoconnect --spec` + `--no-clear` 续画 | 每次完整运行可完成 7~12 个器件，断点可续 | 采用了“慢、稳、可续”策略 |
| T11 | 经过 3 次 `--no-clear` 续跑 | 27 个器件全部放置并连线，网表与 SPEC-20 一致，图纸保存 | 任务完成 |

---

## 2. 关键转折点分析

### 2.1 哪里做错了

1. **整体式 raw JS 调用**  
   把 27 个器件、约 150 个 await 操作（create + modify + getAllPins + createNetFlag/Label）塞进一个 `debug exec`，使连接器的单条请求队列满载。这是第一次失败的主因。

2. **使用 `sch_PrimitiveComponent.modify()`**  
   早期将位号赋值单独做 `modify`。实测该操作在 connector v1.0.4 / daemon v1.1.1 下会触发连接器降级，应直接在 `sch place` 时用 `--designator` 原子赋值。

3. **使用 `eda.lib_Device.getByLcscIds()`**  
   该 API 会打开 EasyEDA Pro 的库浏览器面板（显示 154 万条结果），显著消耗连接器资源，导致后续放置超时。

4. **降级后继续重试**  
   未遵守 daemon 的“假失败定律”警告，持续发送请求，使失败率从 35% 攀升到 45%，最终完全卡死。

5. **未在第一时间识别 typed action 路径**  
   `easyeda sch place` / `sch autoconnect` / `sch list` 等 typed action 走 `/action` 路由，稳定性远高于 `debug exec`，但前期只把 typed action 当作“debug 失败后的测试”，没有快速全面转向。

### 2.2 哪里做对了

1. **快速切换到 typed action**  
   在确认 `sch place` 稳定后，全面重构脚本，不再依赖 raw `debug exec` 做绘图操作。

2. **使用离线 `easyeda lib search`**  
   替代 `getByLcscIds`，避免打开库浏览器，稳定解析 18 个 C 编号。

3. **批量 autoconnect（`--spec` JSON）**  
   把一个器件的所有引脚连接合并为一次 `sch autoconnect` 调用，显著降低操作次数。

4. **断点续画（`--no-clear` + 按位号去重）**  
   脚本能识别已放置器件并跳过，连接器恢复后重跑即可继续，无需清页重画。

5. **位号原子赋值**  
   `sch place --designator` 避免了 `modify` 的降级问题。

### 2.3 用户的纠正

- 用户在连接器完全卡死后主动说“已经退出重进”，重启 EasyEDA Pro 使连接器恢复。这一操作直接解锁了后续 typed-action 路径的验证与成功。

---

## 3. 量化影响

| 指标 | 数值 | 说明 |
|------|------|------|
| 废弃/超时请求 | ~8 条 | 主要是 `debug exec` 整体式与 `modify` 相关 |
| 完整重跑次数 | 3 次 | 每次因连接器降级中断后 `--no-clear` 续画 |
| 调试连接器时间 | ~30–40 分钟 | 含 daemon 重启、GUI 检查、尝试 doc reload 等 |
| 图纸最终结果 | 27 器件 / 全部 net 正确 / 已保存 | 无返工风险，但过程重复消耗 |
| 风险暴露 | 中等 | 未损坏既有文件，但产生了脏页与未保存中间态 |

---

## 4. 结论

本案例的核心教训是：**在 EasyEDA Pro 连接器版本不匹配（v1.0.4 vs daemon v1.1.1）且负载敏感时，应避免 raw `debug exec` 长任务，优先使用 typed action（`sch place`、`sch autoconnect`、`lib search`），并设计可断点续画的幂等流程。**
