# EDA Skill 矩阵 · 八环全生命周期索引（工单219 任务三）

> 日期：2026-10-08 ｜ 仓内 skill 目录 `skills/easyeda-*` + `skills/eda-*`；
> Hermes 侧 skill（hardware-sourcing / hardware-shopping-list / jlcpcb）以互引方式协作，不重复实现。
> 触发词已与既有两件（autodraw / clearance-fix）交叉校验，无冲突无重叠。

## 八环 × skill 对照总表

| 环 | skill | 位置 | 触发语（用户说什么） | 上游交接（谁接棒） |
|---|---|---|---|---|
| ① 选型 | **easyeda-component-sourcing**（本单） | 仓内 | "选个主控 / 用什么芯片 / 找替代料" | → ②：C 编号进网表 |
| ② 画原理图 | easyeda-schematic-autodraw（既有） | 仓内 | "把网表画成原理图 / 画图" | → ③：同步 PCB |
| ③ PCB 布局布线 | **easyeda-pcb-layout-route**（本单） | 仓内 | "布局 / 布线 / 进 PCB / 自动布线" | → ④：布局前仿真其实是**并行前置**；完 → ⑤ |
| ④ 仿真验证 | **easyeda-ngspice-sim**（本单） | 仓内 | "仿真 / 验证电源 / AC 分析 / 看增益" | 与 ③ 并行（布局前）；失败回 ② 改图 |
| ⑤ 修间距 | easyeda-clearance-fix（既有） | 仓内 | "修 DRC / 间距报错 / 丝印冲突" | ≤20 孤立错误修之；>20 回 ③ 重布局 |
| ⑥ 生产产出 | **easyeda-fab-output**（本单） | 仓内 | "出 BOM / 出 Gerber / 准备打样" | 三件套 + 核对单 → Hermes `jlcpcb`（下单） |
| ⑦ 采购下单 | jlcpcb / hardware-shopping-list | **Hermes 侧** | "下单 / 打样 / 追踪订单" | 收 ⑥ 的产出 |
| ⑧ 归档复刻 | **eda-knowledge-retrieval**（本单） | 仓内 | "上次怎么画的 / 查历史 / 以前多少钱" | 查到 → 回注 ②③；parasite-export 持续入库 |

另有跨环协作：Hermes 侧 `hardware-sourcing`（需求调研/跨渠道初选）在 ① 的**上游**。

## 触发词冲突校验（与既有两件）

| skill | 独占触发词 | 边界规则 |
|---|---|---|
| schematic-autodraw | "画原理图 / 网表→图" | 只管原理图；PCB 相关全归 layout-route |
| clearance-fix | "修 / 修 DRC / 修间距" | 只管**事后修**；"布局/布线/重摆"归 layout-route |
| pcb-layout-route | "布局 / 布线 / 进 PCB" | >20 错误重布局的入口；≤20 转 clearance-fix |
| ngspice-sim | "仿真 / AC/DC/瞬态" | 只管电路正确性；DRC 归 ③⑤ |
| fab-output | "出 BOM/Gerber/打样准备" | 只管 EDA 内产出；"下单"转 Hermes |
| component-sourcing | "选型 / 替代料" | 只管 EDA 库落地；调研转 Hermes |
| knowledge-retrieval | "查历史 / 上次 / 以前" | 只查已入库数据；公开资料走 web |

无重叠冲突 ✓（每条触发词唯一归属；边界规则写进各 SKILL.md 的 "When to Use / 不要用于"）。

## 交接链总图

```
hardware-sourcing(Hermes)
      │ 候选清单
      ▼
①sourcing ──C编号──► ②autodraw ──网表──► ④ngspice-sim ──失败改图回②──┐
                              │  通过                              │
                              ▼                                    │
                      ③layout-route ◄──>20错误重布局── ⑤clearance-fix
                              │ DRC 清零
                              ▼
                      ⑥fab-output ──三件套──► ⑦jlcpcb(Hermes) 下单
                              │ 归档（parasite-export → /api/eda/ingest）
                              ▼
                      ⑧knowledge-retrieval ──经验回注──► ②③
```

## 实测状态

| skill | 实测验证 | 状态 |
|---|---|---|
| schematic-autodraw / clearance-fix | 既有（已实战） | ✅ |
| component-sourcing | 步骤写明（LoRaCanary BOM 复核） | 待实测（skill 内含步骤） |
| pcb-layout-route / ngspice-sim / fab-output / knowledge-retrieval | 各 SKILL.md 末节含断言式步骤 | 待实测（依赖 218 的 SPEC-A/B 落地 + 一块真板） |
