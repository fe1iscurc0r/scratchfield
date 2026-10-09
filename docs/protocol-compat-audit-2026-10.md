# 跨领域协议兼容审计 · 六线矩阵（工单216）

> 日期：2026-10-08 ｜ **先审计后立项，本单零实装、零依赖引入**
> 证据等级标注：🔬=真实执行代码路径 / 📖=源码实读 / 🌐=网络实测（API 调用）/ 📁=文件系统实查

---

## 0. 一页结论（按风险倒序 = 按需要动作的紧迫度）

| # | 线 | 判定 | 三选一结论 | 优先级 |
|---|---|---|---|---|
| 1 | LLM 供应商表 | 🟢 **实测通过，非坑**（zhipu/minimax 走 openai 兼容路由正确） | **不动**（补 provider 注册表 = 接口预留，见 §1） | P3 |
| 2 | 消息渠道 | 🟡 抽象已备、QQ/微信在 NEKO 侧 | **接口预留**（ChannelMessage 补 2 字段即可覆盖） | P2 |
| 3 | 科学数据格式 | 🔴 CIF/PDB/xyz **零读写器**（grep 实证） | **接口预留**（最小适配集 = xyz/CIF/SDF，借 ASE extras） | **P1** |
| 4 | OTLP 遥测 | 🟢 字段映射可行（自研 JSON → OTLP 语义一一对应） | 不动（无 Grafana/Jaeger 消费方） | P4 |
| 5 | 存储/同步 | 🟡 http_share 全手工；WebDAV/S3 客户端零命中 | 不动（等 Gitee 配额决策后一起看） | P4 |
| 6 | 语音 realtime | 🟡 voice_mcp_bidi 是 **mlx-audio 本地链**，非 OpenAI Realtime 协议——"适配深度"问题**不成立** | 不动（NEKO 侧才是 realtime 线） | P4 |

**排序理由（用户近期路线图触碰概率）**：材料线本科数据快通道（工单213 刚落地）**马上要吃**原子坐标格式
→ 线 3 第一；渠道统一是 SPEC-11 gateway 的活 → 线 2 第二；GLM 切换 10-10 就到但**实测证明不是坑**
→ 线 1 降级为"注册表预留"；OTLP/存储/语音**没有消费方在排队** → 不动。

---

## 1. 线 1 · LLM 供应商表 —— 🟢 实测通过（非坑），降级

**嫌疑**：`_real_providers`（`apiserver/llm_service.py:258`）硬编码 5 家
（openai/deepseek/gemini/openrouter/anthropic），zhipu/minimax 不在表内。

**🔬 真实代码路径实测**（`build_model_name` 真跑 + `litellm.get_llm_provider` 真解析，2026-10-08）：

| 配置 | 产出 model_name | litellm 路由 |
|---|---|---|
| tokenrhythm 网关 + deepseek（现行） | `openai/deepseek-v4-pro-0813` | openai |
| zhipu 端点，provider=openai / **zhipu** / auto（三种都试） | **全部 `openai/glm-4.7-flash`** | **openai** |
| minimax 端点，provider=openai / auto | `openai/MiniMax-M2.7` | openai |
| deepseek 官方，provider=deepseek（对照） | `deepseek/deepseek-chat` | deepseek |

**判定**：zhipu/minimax 不在 `_real_providers` → 走 `build_model_name` 的 base_url 推断 →
兜底分支（`system/llm_params.py:158-160` 的 else）→ `openai/` 前缀 → **OpenAI 兼容客户端**。
两家都有 OpenAI 兼容端点（工单210 的切换器预设就按此设计）→ **行为正确，不是坑**。
真正的行为差异：deepseek 显式 provider 时会走 litellm 的**原生 deepseek 客户端**（`deepseek/` 前缀），
zhipu/minimax 走 openai 兼容——**两者都能工作**，只是认证头构造路径不同（litellm 内部处理）。

**边界（如实）**：本机无 zhipu/minimax API key → **端到端（真实拿响应）未测**；
已实测的是请求构造层（模型名拼接 + provider 路由解析）。GLM 订阅到期切换时按
`tools/switch_llm_provider.py` 走（工单210），首次切换后跑一次冒烟对话即可闭环。

**接口预留（若未来要注册表化）**——参考 Hermes config.yaml providers 结构：

```python
# system/llm_params.py（草案，不实装）
PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    # ProviderSpec(prefix="openai", endpoint_style="openai_compat", env_key="ZHIPU_API_KEY", ...)
    "zhipu":   ProviderSpec(...),   # openai 兼容端点
    "minimax": ProviderSpec(...),   # openai 兼容端点
}
# build_model_name 的硬编码分支收敛为查表；未注册 provider 落 openai 兼容兜底（现行为不变）
```

## 2. 线 2 · 消息渠道 —— 🟡 接口预留（补 2 字段）

**📖 实查**（`apiserver/channels/__init__.py`）：apiserver 侧 = **WebhookChannel + TelegramChannel**
两实现 + `BaseChannel` 抽象（normalize → ACL → `message_queue.push` → `send_reply`）+
`ChannelRegistry`（DCL 单例，工单222 加锁）。自注第 5 行明确"NEKO 插件侧有 bilibili/qq/wechat，
Lumo apiserver 无统一入口"。

**渠道矩阵**：

| 渠道 | 实现位置 | ChannelMessage 可覆盖？ |
|---|---|---|
| Telegram | apiserver `channels/`（长轮询） | ✅ 已覆盖 |
| Webhook | apiserver `channels/`（通用 POST） | ✅ 已覆盖 |
| QQ（QQbot） | **NEKO 插件侧** | 🟡 差 **平台侧用户标识**（QQ 号/openid）与**富媒体附件回投**字段 |
| 微信（weixin iLink） | **NEKO 插件侧** | 🟡 同上 + **被动回复时限**（微信 5s 硬限，需 async 回投） |

**三选一：接口预留**——`ChannelMessage` 补 `platform_user_id: str` 与 `attachments: list` 两字段
（向后兼容，默认空），QQ/微信适配器等 SPEC-11 gateway 立项时落（渠道统一是 gateway 的核心场景）。

## 3. 线 3 · 科学数据格式 —— 🔴 零适配，接口预留（**本单最高优**）

**📁 grep 实证**（`mcpserver/material_science/` + `apiserver/`，2026-10-08）：

| 格式 | 仓内读写器 | 证据 |
|---|---|---|
| CIF | **0**（命中的 4 文件全是 `specific` 单词的误匹配 + executor_search 的文档字符串） | grep 实证 |
| PDB | **0** | 同 |
| xyz | **0** | 同 |
| MOL2 / SDF / VASP(POSCAR) | **0** | 同 |
| SMILES | ✅ 有（symbolic/encode_eval 指纹/图编码） | 材料线现状 |

**pyproject 无 ASE/pymatgen/openbabel**（命中 5 行全是 ruff 规则号 N803 等，📁 实证）。

**最小适配集（木质素 NPs 工作流最可能用到）**：**xyz**（分子快照/轨迹最小公分母）→
**CIF**（晶体/材料数据库标准）→ **SDF**（带属性的分子库，对接 RDKit——RDKit 已是材料线依赖）。

**三选一：接口预留**（ROS 线同构）：

```python
# mcpserver/material_science/structure_io.py（草案）
class StructureReader(Protocol):
    def read(self, path: str) -> Structure: ...   # Structure = {symbols, positions, cell, metadata}
readers: dict[str, StructureReader] = {}          # 后缀 → reader 注册表；xyz/cif/sdf 各一个可选模块
```
环境变量/安装：`pip install scratchpad[structure]`（extras = `ase`，**一个库同时吃 xyz/cif**；
SDF 另可走 RDKit 路线）。缺依赖时健康检查提示安装（同 ROS 线纪律）。

## 4. 线 4 · OTLP —— 🟢 不动（可行性一句话）

自研 telemetry（`mcpserver/telemetry.py`：tool/duration/ok/caller + 5min 窗熔断计数）映射
OTLP 完全可行：tool 调用 → **span**（name=tool，attributes=caller/agent，status=ok）；
失败率/时延聚合 → **metric**（histogram/gauge）。但**当前无 Grafana/Jaeger 消费方在排队**——
导出器（OTLP HTTP protobuf）价值 = 未来接标准观测栈时零改造。结论：**不动**，真要接时
写 `TelemetryExporter` 协议（照 ros-ecosystem 调研卡的接口层草案格式）一天的事。

## 5. 线 5 · 存储/同步 —— 🟡 不动（等 Gitee 决策）

**📁 实查**：WebDAV/boto3 客户端**零命中**；rsync 4 处命中全是文档/注释（无调用）；
`http_share` 的 18188 端口**在仓内代码零命中**（工单初勘的"18188"是运行时人工约定，不是代码）。
**若要自动分发**：WebDAV 成本最低（PUT 单文件即可，任意 NAS/网盘支持，无 SDK——
`urllib.request` 就能写）；S3 要 boto3+凭证体系，重一档。结论：**不动**——分发痛点与
Gitee 配额问题（记忆：仓库 1261MB 超限待决策）是同一件事，等那个决策一起定。

## 6. 线 6 · 语音 realtime —— 🟡 不动（嫌疑本身不成立）

**📖 实读**（`mcpserver/voice_mcp_bidi/voice_mcp_bidi.py`，362 行）：它是 **mlx-audio 本地链**
（Apple Silicon 的本地 TTS/STT，`mlx_audio` 惰性导入，纯 stdlib 网络层），**不是 OpenAI Realtime
API 客户端**——没有 opus/pcm16/input_audio/session 报文适配（grep 零命中）。
"对 OpenAI Realtime 的适配深度"这个问题**不成立**（对象错了）。
真正的 realtime 语音线在 **NEKO 侧**（`omni_realtime_client/`，工单210 已盘：GLM realtime profile
在 `config/api_profiles.py`）。结论：**不动**；若未来陆墨本体要直连 Realtime API，
按 ros-ecosystem 接口草案格式新立调研。

---

## 附：六线之外的顺手发现

- `channels/__init__.py` 自注（:5）与实际实现**一致**（无文档漂移，好现象）；
- 线 1 实测副产品：`build_model_name` 的 `model_type="router"/"compress"` 分支只判
  `openai.com`（`llm_params.py:122-125`）——router/compress 用非 openai 端点时一律
  `openai/` 前缀。当前 router 只服务网关场景（use_gateway=True），**不是坑**，登记备查。

## 边界

- 线 1 端到端未测（无 key），已测请求构造层（🔬 真实代码路径 + litellm 真实路由解析）；
- 线 2/3/4/5/6 均为静态实查（grep/源码读），未运行时验证；
- 全程零依赖引入、零代码改动（本报告 + probe 脚本是仅有的产物，脚本在 temp 不入库）。
