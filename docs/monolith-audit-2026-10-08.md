# 巨石体检报告（工单209 任务一）

> 日期：2026-10-08 ｜ 方法：**测量而非猜测** —— `tools/monolith_metrics.py`（AST 静态测量，只读）
> 复现：`cd "D:/my git/scratchpad" && CODEBUDDY_SAFE_DELETE_ENABLED=0 .venv/Scripts/python.exe tools/monolith_metrics.py --json`
> 扫描范围：仓内 6310 个 `.py`（**不含** `NEKO/`、`frontend/`、`.venv`）
> **本报告不做任何拆分**（工单明令：只给论证 + 方案，等拍板再开执行单）。

---

## 0. 实测数据总表（按 import 出度降序）

| 文件 | LOC | 顶层函数 | 类 | **import 出度** | 最长函数 | 最长函数行数 |
|---|---|---|---|---|---|---|
| **`system/config.py`** | **2098** | 56 | 52 | 🔴 **138** | `build_context_supplement` | 154 |
| `apiserver/travel_service.py` | 1306 | 54 | 6 | 🔴 **66** | `analyze_history` | 107 |
| `apiserver/routes/chat.py` | 1269 | 19 | 2 | 🟡 14（多为 tests） | **`chat_stream`** | **537** |
| `agentserver/openclaw/openclaw_client.py` | 1547 | 49 | 6 | 🟢 5 | **`OpenClawClient.send_message`** | **371** |
| `agentserver/openclaw/instance_manager.py` | 1518 | 65 | 2 | 🟢 5 | **`InstanceManager.send_message_stream`** | **248** |
| `agentserver/openclaw/embedded_runtime.py` | 1015 | 51 | 1 | 🟢 8 | `EmbeddedRuntime.start_gateway` | 86 |
| `coupled/omnilimb-face/omnilimb_face/runtime.py` | 1911 | 64 | 4 | ⚪ **0** | `VTuberRuntime.tool_say` | 90 |
| `build.py` | 1766 | 69 | 0 | ⚪ **0** | `preinstall_openclaw` | 98 |

**与工单初勘的偏差（实测更正）**：`system/config.py` 2042 → **2098**（工单209 出单前 + 工单222 的 `atomic_write_json` 与 LF 归一化）；
`openclaw_client` 1540 → 1547；`instance_manager` 1517 → 1518；`embedded_runtime` 1008 → 1015；`runtime.py` 1910 → 1911；`build.py` 1765 → 1766。

---

## 1. 🔴 标红：`system/config.py` 是全系统单点

```
被 138 个文件 import  ← 全仓第一（第二名 travel_service 66，第三名 chat.py 14）
最长函数仅 154 行     ← 它不是「函数巨石」，是「**表面积巨石**」：56 函数 + 52 个 pydantic 模型
```

**实测含义**：它的痛不在单个函数难读，而在**任何模块改动都要碰它** —— 138 个 import 方意味着
任何签名/常量/模型字段的改动都是全系统面。它同时也是 LOC 榜第一（2098）与出度榜第一（138），**两个榜都是第一**。

> ⚠️ **执行单第一步必须是「先加回归测试网，再拆」**（工单要求标红，本报告确认这条判断成立）：
> 需要一个 `tests/test_config_surface.py` 钉住 —— ①`system.config` 的公共符号集合（`dir()` 差集，
> 防搬块时漏 re-export）；②关键访问器行为（`get_config` / `get_config_path` / `get_server_port` /
> `AI_NAME`）；③`atomic_write_json` 的原子性（工单222 已建，可复用）。

### 拆分方案（不执行，供拍板）

**边界（按关注点切，`system/config_parts/`）**

| 新模块 | 覆盖 | 依据（实测） |
|---|---|---|
| `paths.py` | `_get_user_data_dir` / `get_data_dir` / `_get_app_dir` / `get_config_path` / `_get_local_config_path` / `_get_project_config_template_paths` | 纯路径解析，无模型依赖，**可第一个搬** |
| `writers.py` | `atomic_write_json` / `sync_source_config_to_runtime` / `detect_file_encoding` | 工单222 刚收口成单一写入口，边界天然 |
| `schema.py` | 52 个 pydantic 模型 + `CONFIG_SCHEMA_VERSION` + 校验器 | 最大一块，但是**叶子**（被访问器依赖，不反向依赖） |
| `prompts.py` | `get_prompt_manager` + 提示词相关（`build_context_supplement` 154 行在内） | mind/chat 线专用 |
| `ports.py` | `ServerPortsConfig` / `get_server_port` / `get_all_server_ports` / `_get_runtime_server_ports` | 启动期专用，边界清晰 |
| `__init__.py`（门面） | **re-export 上述全部**，保留 `from system.config import X` 的 138 个调用方**零改动** | 兼容红线 |

**迁移顺序**：`paths` → `writers` → `ports` → `prompts` → `schema`（由叶子到中枢）；每搬一块跑一次回归网。
**兼容 shim 策略**：`system/config.py` 保留为薄门面（`from .config_parts.X import *` + 显式 `__all__`），
**不搞双源**（不给旧符号留副本，避免两处定义漂移）。

---

## 2. 优先级论证（价值 vs 风险，两个维度分开看）

| 序 | 目标 | 为什么 | 风险 |
|---|---|---|---|
| **①** | `chat.py::chat_stream`（**537 行单函数**） | **函数级拆分**，改的是"一个函数的内部结构"，不动 import 面 → 收益最高、风险最低 | 🟢 低（14 个 import 方，且多为 tests） |
| **②** | `openclaw_client::send_message`（371 行）+ `instance_manager::send_message_stream`（248 行） | 同样是**函数级**，且只被 5 个文件 import | 🟢 低（5 importers） |
| **③** | `travel_service.py`（1306 / 66 importers） | 文件级拆分，按「会话生命周期 / 提示词构建 / 事件提取 / 历史分析」切 4 块 + 门面 re-export | 🟡 中（66 importers，但最长函数仅 107 行 = 无函数级巨石） |
| **④** | `system/config.py`（2098 / **138 importers**） | **价值最高**（改动频率第一）但**风险最高** | 🔴 **高 → 必须最后做，且先建回归网** |
| **⑤** | `coupled/.../runtime.py`（1911 / **0 importers**）、`build.py`（1766 / **0 importers**） | 独立子系统 / 脚本，**0 个仓内 import 方** → 拆了没人受益，改动频率低 | ⚪ 建议**延后**（可容忍） |

**一句话结论**：**先拆函数，再拆文件；先拆低出度，最后拆 `system/config.py`**。
本仓的"巨石"其实是两类病 ——
- **函数巨石**（`chat_stream` 537 / `send_message` 371 / `send_message_stream` 248）→ **函数级拆分即可，风险可控**
- **表面积巨石**（`config.py` 138 importers / `travel_service` 66）→ 需要文件级拆分 + 门面 re-export，**先有回归网**

---

## 3. 未做（明确边界）

- **未执行任何拆分**（工单要求：只给论证 + 方案，等用户拍板）。
- 未动 `coupled/` 与 `build.py`（0 importers，判为可容忍）。
- 未统计运行时开销 / 内存（静态测量只回答"结构与耦合"，不回答"性能"）。

## 4. 工具

`tools/monolith_metrics.py`：AST 测量 LOC / 顶层函数数 / 类数 / 最长函数 Top5 / **import 出度（含名单）**。
加新目标只需往 `TARGETS` 加一行；`--json` 供 CI/后续脚本消费。**幂等、只读、无副作用。**
