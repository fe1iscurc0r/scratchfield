# LESSONS_LEARNED

> 按项目统一编号体系维护。每条教训格式：场景 → 失败模式 → 正确做法 → 适用条件。

---

## L-01 · 避免在单条 `debug exec` 中堆积大量异步 EDA 操作

- **场景**：需要一次性放置多个器件、设置多个位号、打多个网络标号。
- **失败模式**：把大量 `await eda.*` 操作封装进一段 JS 通过 `easyeda debug exec` 执行，连接器单请求队列被长时间占用，触发“context deadline exceeded”和降级。
- **正确做法**：拆分为一次只处理 1 个器件或 1 个小任务的多个独立调用；对 EasyEDA 优先使用 typed action（`sch place`、`sch autoconnect`、`sch list`），它们走 `/action` 路由，稳定性更高。
- **适用条件**：通过 easyeda-agent 自动化绘制原理图/PCB 时；连接器版本不匹配或负载敏感时尤其如此。

---

## L-02 · 连接器降级时立即停止并等待，不要盲试

- **场景**：daemon 返回“connector looks DEGRADED under load”或“context deadline exceeded”。
- **失败模式**：继续快速重发请求，使失败率从 35% 一路攀升到 45%，最终单请求队列完全卡死。
- **正确做法**：
  1. 停止一切写入操作；
  2. 等待 20–60 秒；
  3. 做一次轻量只读（如 `easyeda health` 或 `sch list`）验证连接器恢复；
  4. 再继续，且降低速率。
- **适用条件**：任何与 EasyEDA Pro / 嘉立创 EDA 专业版的自动化交互。

---

## L-03 · 器件库查询用离线 `lib search`，避免 `getByLcscIds` 打开库浏览器

- **场景**：根据 LCSC C 编号查询器件库 UUID。
- **失败模式**：使用 `eda.lib_Device.getByLcscIds()` 会触发 EasyEDA Pro 打开“库浏览器”面板，展示大量搜索结果，占用连接器资源并导致后续放置超时。
- **正确做法**：使用 `easyeda lib search --query Cxxxx --limit 1`，它在离线完成查询，不打开 UI。
- **适用条件**：需要把 LCSC C 编号解析为 libraryUuid + deviceUuid 的所有场景。

---

## L-04 · 设置位号用 `sch place --designator`，避免 `modify` 触发降级

- **场景**：放置器件后需要把自动位号改为 J1/R1/U1 等。
- **失败模式**：用 `eda.sch_PrimitiveComponent.modify(id, {designator: ...})` 在 connector v1.0.4 下会触发连接器降级。
- **正确做法**：在 `easyeda sch place` 时直接传 `--designator`，原子地完成放置和位号赋值。
- **适用条件**：需要通过 easyeda-agent 自动化放置器件并指定位号。

---

## L-05 · 设计 EDA 自动化脚本时优先考虑幂等与断点续画

- **场景**：长流程运行到一半因连接器降级中断，需要重跑。
- **失败模式**：脚本每次从头清空页面重画，中断后已做工作丢失，且重跑会重复放置器件。
- **正确做法**：
  1. 脚本先读取当前图页已有的 designator 集合；
  2. 对已存在的器件跳过放置，仅执行幂等的后续操作（如 `sch autoconnect`）；
  3. 提供 `--no-clear` 参数支持续跑；
  4. 操作间加入 1.5–3 秒 sleep 降低连接器负载。
- **适用条件**：任何可能被连接器降级打断的多步骤 EDA 自动化流程。

---

## L-06 · 使用 `sch autoconnect --spec` 批量连接引脚

- **场景**：为一个器件的多个引脚分别连接电源/地/信号网络。
- **失败模式**：逐个调用 `sch autoconnect` 增加请求次数，加速连接器降级。
- **正确做法**：生成 JSON 规格 `{connections: [{pin, kind, net}, ...]}`，通过 `--spec` 一次性提交给 `sch autoconnect`。该命令还是幂等的，已连到目标网络的引脚会被跳过。
- **适用条件**：原理图绘制中需要将一个器件的多个引脚挂到同名网络；适合批量打 netflag/netport。

---

## L-07 · 对“假失败”保持警惕，先读取状态再决定是否重试

- **场景**：请求返回 `context deadline exceeded`，但工作可能已经落地。
- **失败模式**：直接重试导致重复放置器件或重复打标号。
- **正确做法**：重试前先用轻量只读（如 `sch list`）确认目标状态；只有确认未落地时才重试写入；对写入操作尽量使用幂等接口。
- **适用条件**：连接器不稳定、经常出现超时但结果可能已落地的场景。

---

## L-08 · 修改既有布线前必须先做“层/网络拓扑快照”

- **场景**：对已经 route 过的板子做局部 clearance/track 修改。
- **失败模式**：只看坐标就用 `pcb track` 重画，没发现原线在 Bottom 层，结果画到 Top 层与 GND 短路，错误从 6 个暴增到 12 个。
- **正确做法**：先用 `pcb dump` + `track-list` + `via-list` 导出每条线段的 `layer`、`net`、`start/end`、`width` 和 via 拓扑，确认原走线所在层和连接关系再改。
- **适用条件**：任何非全板 rip-up 的布线微调。

---

## L-09 · 布线编辑过程中不要穿插 `doc reload`

- **场景**：用 EasyEDA Pro CLI 连续改线、修 clearance。
- **失败模式**：每次 `doc reload` 都会使 routing stage 授权失效，必须重新 `set-assembly → layout-lint --gate → confirm-layout → confirm-outline`，大量消耗 token 且容易出错。
- **正确做法**：所有 `track/via/delete` 在一个 batch 内完成，只在最终 `pcb check` 前 reload 一次。
- **适用条件**：使用 CLI daemon 模式进行多步布线修改。

---

## L-10 · assembly profile 必须匹配实际工艺，不能用 0 mil 绕 gate

- **场景**：`pcb layout-lint --gate` 因 hand-solder 40 mil 间隙而失败。
- **失败模式**：把 profile 改成 reflow、`min-gap=0`、`large-pad-access=0` 强行过 gate，导致后续装配/可焊性审查失效。
- **正确做法**：compact SMT 板使用 **reflow + 6 mil（0.15 mm）电气间距**；插件/手焊板才需要 40 mil。
- **适用条件**：小尺寸 IoT 板、以 SMT 器件为主的场景。

---

## L-11 · delete/rip-up 后必须重新授权 routing stage

- **场景**：删除/rip-up 走线后继续 create track。
- **失败模式**：`pcb track` 返回 `STAGE_BLOCKED: missing outline_confirmed, pre_route_passed`。
- **正确做法**：删除操作会重置 routing 授权；再次 create 前必须重新 `set-assembly → gate → confirm-layout → confirm-outline`。
- **适用条件**：任何先删后建的 CLI 布线流程。

---

## L-12 · 最终验收优先使用 `pcb check` 而非 `pcb drc --json`

- **场景**：最终 DRC 验证。
- **失败模式**：`pcb drc --json` 多次返回 `unexpected end of JSON input`，无法解析。
- **正确做法**：用 `pcb check --json`，读取顶层 `findings` 数组，按 `level` 过滤 ERROR/WARN。
- **适用条件**：CLI 验收阶段。

---

## L-13 · 布线越修越碎时必须立即停手并回退

- **场景**：用 CLI 补丁式修复 PCB 走线/clearance/open。
- **失败模式**：反复 `create_track`/`delete`/`create_via` 补小段，坐标微小错位导致碎铜越来越多；原本 2 个 NoConn 补成 8 个，DRC 不降反升。
- **正确做法**：
  1. 每次修改后立即对比 **修改前 vs 修改后的 NoConn 数量和具体对象**；
  2. 若发现 NoConn 数量增加或新增了原本不存在的对象，立即**撤销本次写入**（`track-delete`/`via-delete`/`rip-up` 回退到上一步已知较好的状态）；
  3. 停止补丁，改用**整网 rip-up + 自动布线**（`route-short` / `route-critical` / 原生 autoroute）从头来；
  4. 回退后向用户报告当前真实状态，让用户决定是否继续自动布线或接管手动修。
- **适用条件**：任何 CLI 布线修补，尤其是电源/差分等关键网络；板上高密度区域（U3、USB-C、天线附近）尤其如此。

