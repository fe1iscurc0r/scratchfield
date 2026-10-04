# NEKO × 陆墨融合指导书 v1.1 多智能体终审纪要

**讨论日期**: 2026-08-01
**指导书**: docs/NEKO-Lumo-Fusion-Blueprint-v1.1.md
**参与智能体**:
- 铁锚 (kimi2.7code) — 代码改动点准确性验证
- 实验田维护者 (deepseekv4pro) — 安全前置与降级链完整性验证
- 杜赞 (GLM5.2) — 路线图可执行性 + GO/NO-GO 决策
- Hermes (千问3.7plus) — 协调与汇总

---

## 一、三方一致结论：方向对，但需补 4 项才能 GO

**战略方向**：v1.1 的 5 处硬伤修正方向全部正确，无根本性架构错误。

**战术落地**：4 项落地灰区会让 M1 启动即卡壳。补完即可推进，不需推倒重来。

**综合判定**：**条件性 NO-GO** — 补 4 项后 GO。

---

## 二、三方一致发现的 3 个阻塞项

### 阻塞 1：鉴权链路（LUMO_PROXY_TOKEN）代码零实现

**三方共识**：
- 铁锚：现有 `require_local_auth` 不认共享密钥，需新建独立依赖
- 实验田维护者：全仓库 grep 零实现，现有 openai_proxy 端点零鉴权
- 杜赞：现有鉴权是用户登录 token 体系，与进程间共享密钥是两套机制

**修复方案**（杜赞建议）：
1. scratchpad 新建 `require_proxy_token` 依赖（独立于 `require_local_auth`）
2. 从 `os.getenv("LUMO_PROXY_TOKEN")` 读密钥，常量时间比较
3. NEKO 进程通过启动脚本（lumo.ps1）注入同一环境变量
4. persona-aware 端点用 `Depends(require_proxy_token)`

---

### 阻塞 2：铁律3豁免范围不够（monitor + memory_server 都需改源码）

**三方发现**：
- 实验田维护者：monitor.py:513 改 127.0.0.1 需改源码，但不在豁免内 → 逻辑死结
- 杜赞：关 memory_server 需改 `launcher_core/runtime.py` 的 SERVERS 列表 + _CRITICAL_MODULES，也违反铁律3
- 铁锚：未直接发现，但确认 monitor.py 硬编码 0.0.0.0

**修复方案**（杜赞建议，推荐）：
**写 `neko_launcher_wrapper.py`** — import 后 monkey-patch `SERVERS` 列表 + 监听地址，再调 `start_launcher`。
- 代价低
- 零源码修改
- 铁律3 不动摇
- 上游更新时 wrapper 重放即可

**替代方案**：扩大铁律3豁免声明，把 monitor.py + runtime.py 列入 local-patch。但会让豁免扩大化，腐蚀铁律3刚性。

---

### 阻塞 3：M1 端点路径冲突

**铁锚发现**：openai_proxy 已注册 `/v1/chat/completions`（透传给 OpenClaw 使用）。M1 新建同名 persona-aware 端点会冲突——FastAPI 后注册覆盖前者，破坏 OpenClaw 工具调用链路。

**修复方案**（铁锚建议，三选一）：
- **选项A（推荐）**：新端点换路径 `/persona/v1/chat/completions`，NEKO 指向新路径。变更量小，无回归。
- 选项B：在现有端点内按认证方式分流（LUMO_PROXY_TOKEN 命中走 persona 分支）。耦合两类逻辑。
- 选项C：替换 openai_proxy 实现。影响大。

---

## 三、三方分歧

### 分歧 1：M3 注入端点

- **杜赞**：proactive_router 只是配置读写，不是说话注入端点。M3 需找/建注入端点。
- **实验田维护者**：建议用 NEKO main_server 已有 REST 路由。
- **铁锚**：未深入。

**Hermes 建议**：M3 启动时先排查 NEKO 现有 REST 路由（vmc_router/system_router/emotion），若无合适端点则新建 `lumo_inject_router.py`（走 wrapper 或列入豁免）。

### 分歧 2：emotion "本地小模型"描述

- **实验田维护者**：v1.1 说"emotion_model 本地小模型"，实际代码调用配置的 LLM API（可能云端）。
- **杜赞/铁锚**：未深入。

**Hermes 建议**：v1.2 勘误为"配置的 emotion 模型"。若要严格本地，需把 emotion_config 指向本地 Ollama。

---

## 四、其他发现（非阻塞）

| # | 问题 | 来源 | 严重度 |
|---|------|------|--------|
| 1 | E7 表述错：48915 是 TOOL_SERVER_PORT，不是"未硬编码" | 铁锚+杜赞 | MEDIUM |
| 2 | telemetry_server(8099) + survey_server(8100) 0.0.0.0 漏标 | 实验田维护者 | MEDIUM |
| 3 | D1 降级链：scratchpad 挂了 NEKO 失能，无 fallback brain | 实验田维护者 | MEDIUM |
| 4 | .upstream-sha 文件未创建 | 实验田维护者 | LOW |
| 5 | 双 persona 源（NEKO 本地 persona 路由未处置） | 杜赞 | LOW |
| 6 | openai_proxy 现有端点零鉴权（v1.0 既有问题） | 实验田维护者 | LOW（本地缓解） |
| 7 | overlay 机制复杂度被低估（merge 语义未定义） | 杜赞 | MEDIUM |
| 8 | 单机资源瓶颈未量化（天选7pro 内存/显存未记录） | 杜赞 | MEDIUM |

---

## 五、v1.0 硬伤修复验证表

| # | 硬伤 | v1.1 修正 | 验证结果 |
|---|------|----------|---------|
| 1 | CUA 路径错 | 改 computer_use.py:1182-1191 | ✅ 代码实测命中 |
| 2 | proxy 不带人格 | 新建 persona-aware 端点 | ✅ 方向对，待实现（注意路径冲突） |
| 3 | memory 关闭 | 不启动进程 | ⚠️ 需 wrapper 或扩豁免 |
| 4 | M3 协议 | 改 REST | ✅ 方向对，注入端点待指定 |
| 5 | 鉴权 | LUMO_PROXY_TOKEN | ⚠️ 代码零实现，需新建 |

**勘误验证**：6/7 一致，E7 表述部分错误。

---

## 六、必须补齐的 4 项（补完即 GO）

| # | 补齐项 | 实施方 | 优先级 |
|---|--------|--------|--------|
| 1 | 写 `neko_launcher_wrapper.py`（patch SERVERS + monitor host） | scratchpad | P0 |
| 2 | 新建 `require_proxy_token` + persona-aware 端点（换路径） | scratchpad | P0 |
| 3 | 指定 M3 注入端点（排查现有 REST 或新建） | 指导书 v1.2 | P1 |
| 4 | 处置 NEKO 本地 persona 路由（禁用或只读） | 指导书 v1.2 | P1 |

---

## 七、修复后执行路径

| 步骤 | 动作 | 验证 |
|------|------|------|
| 1 | 写 `neko_launcher_wrapper.py` | 启动后 netstat 确认 48913 只监听 127.0.0.1，48912 无进程 |
| 2 | 新建 `require_proxy_token` + persona-aware `/persona/v1/chat/completions` | curl 带 token 返回陆墨人格回复，不带返回 401 |
| 3 | NEKO api_providers.json overlay 注入 lumo provider | NEKO 输入 → 显示陆墨回复（M1 验证标准） |
| 4 | 处置 NEKO 本地 persona 路由 | NEKO 角色卡只剩外观/语气，人格来自陆墨 |
| 5 | 补 v1.2 指导书：4 项灰区落定 + E7/emotion 勘误 | 实验田维护者审签 |

**第一个可上线里程碑**：M1（文本打通）。补完 4 项后即可开工。

---

## 八、总结

**v1.1 修正方向 5/5 正确**，无根本性架构错误。但 4 项落地灰区会让 M1 启动即卡壳：

1. 鉴权零实现 → 新建 `require_proxy_token`
2. 铁律3豁免不够 → 写 wrapper（零源码修改）
3. M1 端点冲突 → 换路径 `/persona/v1/chat/completions`
4. M3 注入端点空白 → 排查现有 REST 或新建

**补完 4 项后即可推进 M1**。预计 3-5 人天完成 M1 文本打通。

---

*纪要由 Hermes (千问3.7plus) 协调生成，铁锚 (kimi2.7code) / 实验田维护者 (deepseekv4pro) / 杜赞 (GLM5.2) 并行审查。*
