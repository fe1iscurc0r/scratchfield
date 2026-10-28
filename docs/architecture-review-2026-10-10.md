# 架构体检报告 2026-10-10（无工单期自主巡检）

> 触发：用户「看看有没有工单做掉，没有的话看看有没有什么架构上的可以优化的点」。
> 工单队列空（227 为最新，已完成）→ 转自主巡检。
> 方法：全部数字均为本机实测（命令与判据写在每节），非推测；未验证项标注边界。

---

## 零、本次已落地（3 类修复，全部有前后对照）

### 0.1 ⭐ NEKO 子树同步缺口修复 → 测试从 20 红转全绿

**发现过程**：memory_maas 的 9 failed + 7 errors 一直被记为「已知账」。本次逐层剥：
`MemoryMaasCore()` → 五件套导入 → **`No module named 'utils.glm_tts'`**。

**根因（实测）**：本仓 `NEKO/N.E.K.O` 是**跨版本快照**，不是单一上游提交的切片：

| 证据 | 数值 |
|---|---|
| 上游 `Project-N-E-K-O/N.E.K.O` main 的 .py | 2943 |
| 本仓 NEKO .py | 16007（**非上游子集**） |
| 上游有而本仓缺 | **496** |
| `utils/cloudsave_runtime/operations.py` vs 上游 | **逐字节相同**（1990 行）→ 该文件是上游最新 |
| `utils/character_memory.py` vs 上游 | 本地 616 行 vs 上游 **941 行** → 该文件落后 325 行 |

即：**同一棵树里并存不同上游修订**。`operations.py`（新）需要
`character_memory.evict_character_runtime_caches`，而本地 `character_memory.py`（旧）没有 →
ImportError 链一路炸到 `memory.*`。

**修复（带备份 + 收敛判定 + 不覆盖本地定制的安全循环）**，只动 2 个 upstream 文件：

| 文件 | 动作 | 说明 |
|---|---|---|
| `utils/http/url.py` | 补齐 | 本地 28 行 → 上游 130 行（含 `same_endpoint` / `endpoint_identity` 端点判据族，被 5 个 NEKO 文件 import） |
| `utils/glm_tts.py` | 补齐 | 上游新文件（被 `main_routers/characters_router/voice_preview.py` import） |
| `utils/character_memory.py` | 刷新 | 616 → 941 行（补 `evict_character_runtime_caches` 等） |

**验证**：
- `pytest tests/test_memory_maas.py` → **17 passed**（原 9 failed + 7 errors + 1 passed）
- `pytest tests/test_spec03_phase1.py` → **11 passed**（原为收集期 ImportError，正是 conftest
  登记跳过的那份 → 该 `--ignore` **可以摘掉**）
- 自查脚本先跑「含本地定制关键词则中止」检查：3 个文件均无本地定制标记（openfang/mijia/lumo…）

**⚠️ 但子树整体仍是混版本**：剩下 496 个上游文件本体缺失、且已见内部 API 漂移。
本次只补了 memory_maas 链所需的最小集。**这是个需要拍板的架构债**（见 §二.1）。

### 0.2 hamlog 适配器被系统代理劫持（真实缺陷）

**发现**：本会话环境有 `http_proxy`（国内访问 GitHub/PyPI 的常见配置），
`test_hamlog_adapter` 2 例失败，报错是
`HamLog API 返回 HTTP 502（GET /qso/search）：upstream connect failed: … (os error 10061)`
——**代理**的措辞。即：调用**本机** HamLog 服务的请求被系统代理拦走，
报错退化成「返回 HTTP 502」而非「不可达」，**真实原因（服务没起）被掩盖**。

**根因**：`mcpserver/adapters/hamlog_adapter/adapter.py` 用裸 `requests.request(...)`，
**未禁用 env 代理**；而仓库**已有同一约定**（内部/本地调用 `trust_env=False`）：
`api_server.py:556`、`event_bus/bridge.py:316`、`local_search.py:75`、`naga_control.py` ×4、
`routes/auth.py:108` —— hamlog 适配器是**漏网的那个**。

**修复**：加模块级 Session（`trust_env=False` + DCL 锁，与仓库单例约定一致）供 `_request` 使用。

**验证（双向对照）**：带 `http_proxy` 跑 → **20 passed**；去代理跑 → **20 passed**（修复前带代理必挂）。
→ 适配器现在**代理无关**。

### 0.3 两个测试把「环境异常」误判为「产品缺陷」

| 测试 | 原判据的问题（实测） | 修法 |
|---|---|---|
| `test_code_workspace::...symlink_denied` | `_make_escape_link` 只看 `os.symlink` 是否抛异常——**Windows 无开发者模式时 os.symlink 不抛异常但产出不可解析链接** → 测试以 `not_found` 假失败（真因：链接建了但穿不透） | 建链后**用探针文件验证真能穿透**，不行再退 junction，都不行才 return False（→ 测试诚实 skip） |
| `test_concurrency_locks::...partial_file` | 把读者的 `PermissionError(13)` 计入 `bad` 并硬断言 → 报「读到非法 JSON 4 次」，但全程**零次 JSONDecodeError**。PermissionError 是 Windows 下 `os.replace` 持有目标时的**瞬时拒绝打开**，不是撕裂读 | 两类错误分离：**JSONDecodeError 硬断言**（这才是原子性）、OSError 单列容忍 |
| `test_planner::...run_in_parallel` | 阈值 0.55s 贴串行下界 0.6s；全量负载下实测墙钟 **0.94s**（线程池冷启动+争用）→ 假失败 | 单分支 sleep 0.2→0.5s 拉开差距、阈值 1.2s（串行 1.5s），结构证据仍由线程数断言给 |

**验证**：`test_concurrency_locks.py` **连跑 6 次 6/6 通过**（修复前约 1/3 概率失败）；
`test_planner` 单跑 3/3 通过。

---

## 一、体检结论（有数字的健康项 —— 无动作）

| 项 | 实测 | 判读 |
|---|---|---|
| **模块级导入环** | 282 个有出边的模块，**SCC>1 为 0** | ✅ 无循环依赖（1754 个模块） |
| **API 鉴权** | 269 条路由，**集中式中间件** `sync_auth_token` 单一收口；公开前缀 14 条路由，其中状态变更 7 条**全是 `/auth/*`** + `/api/status/heartbeat` | ✅ 防线集中且白名单紧凑——**未发现鉴权缺口**（初版我按函数签名扫出「71% 无鉴权」是**假发现**：漏算了中间件与 router 级依赖，已改正） |
| **耦合中心（被 import 次数）** | `apiserver/naga_auth.py` **38×** > `api_server.py` 19× > `telemetry.py` 18× > `tool_schemas.py` 13× = `system/config.py` 13× | 值得留意 `naga_auth` 成为第一热点（38 个模块依赖它） |

---

## 二、待拍板的架构优化候选（按价值排序）

### 1. NEKO 子树：混版本快照（**最高结构债**）
- 现状：496 个上游文件缺；内部 API 漂移（见 §0.1 证据表）。
- 危害：任何依赖 NEKO 的功能（memory_maas、voice_preview、config_manager）都可能在
  「下一个 import」处炸；本次只补了 memory_maas 链。
- 三个选项（需拍板）：
  a. **单点重导入**：把子树整体对齐到某个上游 commit（工程量最大，但一次干净）；
  b. **按需补齐**：继续「炸到哪补到哪」（本次模式）——成本低但债务持续；
  c. **去 vendoring**：把 NEKO 当外部依赖（pip/子模块）——牵动发布边界（NEKO 不随包分发），需评估。

### 2. `naga_auth` 成为 38 个模块的第一耦合中心
- 现象：auth 模块同时承担「token 存取 + 请求上下文 + 网关判定 + 用户信息」四职责。
- 危害：任一责任变更牵动 38 个调用方；测试需大量 patch（本会话已见多处 patch 面）。
- 候选：拆 `naga_auth`（token 存储）与 `naga_context`（请求级上下文/依赖注入），
  `should_use_model_gateway` 归网关层。**先补锚测试再拆**（沿用工单209 方法论）。

### 3. `apiserver/api_server.py`：装配与路由挂载混杂
- 现象：269 条路由中 108 条（apiserver 侧）在此文件挂载；它同时是 app 工厂、中间件宿主、
  静态挂载、内部代理。19 个模块 import 它。
- 候选：把「挂载清单」抽成注册表（`routes/__init__.py: register_all(app)`），
  api_server 只留 app 生命周期 + 中间件（沿用 209 的「薄壳」模式）。

### 4. 本地服务调用统一走「无代理 Session」（本次只修了 hamlog）
- 现象：仓库有 8+ 处 `trust_env=False`，但也有适配器漏网（§0.2）。
- 候选：抽 `mcpserver/internal_http.py`（统一 Session 工厂：trust_env=False + 超时 + 重试），
  适配器一律经它调用本地服务 —— 消除「代理环境行为不一致」这一整类坑。
- 价值：国内用户带代理是**常态**，这类 bug 只会越来越多。

### 5. 测试卫生：`--ignore=tests/test_spec03_phase1.py` 可以摘掉
- 依据：本次修复后该文件 **11 passed**（原收集期 ImportError）。
- 注意：conftest 里若仍登记了它的跳过依据，需同步更新（避免「文档漂移」）。
  另：`test_memory_maas` 等的「已知账」注释也需一并更新——它们**不再是红的**。

---

## 三、验证边界（如实标注）

- 全量数字取自本机 Windows + 本会话环境；**`http_proxy` 已确认会影响若干本地服务测试**
  （修 hamlog 后该影响消除，其余适配器未逐一实测）。
- `test_code_workspace` 的逃逸链接用例在本机**诚实 skip**（workspace 在 D:、pytest tmp 在 C:，
  junction 跨卷不可用）→ **该逃逸防线本机未验证**；建议在 Linux/macOS CI 跑一次补上这一层。
- 未做的项：未跑 lint/类型闸门全量（前端部分本次未触碰）；未做性能压测。
