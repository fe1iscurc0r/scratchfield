# 冷启动基线 2026-10（工单220 任务一）

> 日期：2026-10-08 ｜ 方法：清 `__pycache__` 后 `python -X importtime apiserver/start_server.py`，
> 三次取数（run1/2/3）；解析用临时脚本（importtime 后序树解析）。
> 边界：测的是**模块导入段**；lifespan 内各初始化步骤需启动完整服务观测（本机为生产机未起全量服务，
> 该段沿用卷191-B3 的计时点，未复测——如实标注）。

## 1. 三次数值（模块导入段，apiserver.api_server 累计）

| 跑 | api_server 累计 | 备注 |
|---|---|---|
| run1 | 1725 ms | 首清缓存 |
| run2 | 2134 ms | 每次清 pycache（冷启动口径） |
| run3 | 2123 ms | 同上 |
| **patch 后** | **1466 ms** | ⭐ 见 §3（−668ms） |

> run1 偏快疑似磁盘缓存残留；以 run2/3 为基线（~2.1s）。

## 2. Top 慢模块（run2，cumulative）

| 模块 | 累计 | 占比根因 |
|---|---|---|
| `apiserver.routes.data_tools` | **990 ms** | **pandas 660 ms**（顶层 import） |
| `apiserver.naga_auth` | 427 ms | self 127ms + system.config 链 108ms + httpx/charset 链 |
| `fastapi` | 261 ms | 框架本体 |
| `pandas`（经 data_tools） | 660 ms | data_tools 的主体 |
| `httpx` | 177 ms | 多路由共享 |

## 3. ⭐ 已落地的懒加载 patch（≤20 行、零行为变化，工单授权顺手做）

`apiserver/routes/data_tools.py`：顶层 `import pandas as pd` → `TYPE_CHECKING` 注解 +
运行时 `_pd()` 惰性函数；16 个使用点全在请求处理函数内，首次调用自动加载。

**实测收益**：api_server 导入 **2134 → 1466 ms（−668 ms，超过工单 500ms 门槛）**；
验证：import 后 `'pandas' in sys.modules == False` ✓、惰性调用 DataFrame 正常 ✓、
相关回归 15 passed ✓。

## 4. 懒加载候选表（后续批次）

| 候选 | 预估收益 | 风险 | 建议 |
|---|---|---|---|
| `naga_auth` 的 `cryptography.fernet`（:29） | ~14ms | 低（Fernet 只在加解密时用） | 候选 B（小） |
| `data_tools` 的 `matplotlib.pyplot` | ~200-300ms | 中（模块级 `matplotlib.use("Agg")` 需保序——use 必须在 pyplot 前；可改为函数内） | **候选 A（下批首选）** |
| mcpserver 36 adapter 注册时机 | 实测**不是问题**：导入期 mcpserver 相关仅 ~3ms（manifest 懒加载，卷189-A1 已做） | — | 无需处理 ✓ |
| `naga_auth` 自身 127ms self | 需拆模块 | 中 | 观望（等 209 的 config.py 拆分连带处理） |

## 5. 未测边界（如实）

- lifespan 内步骤计时未复测（需起全量服务）；卷191-B3 有历史点可对照。
- importtime 是单进程口径，未含 uvicorn worker fork。
