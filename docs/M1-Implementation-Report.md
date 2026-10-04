# NEKO × 陆墨融合 M1 补齐工作实施报告

**实施日期**: 2026-08-01
**阶段**: M1 文本打通前置补齐（4 项全部完成）
**参与智能体**:
- 铁锚 (kimi2.7code) — 代码起点确认 + 验证审查
- 实验田维护者 (deepseekv4pro) — 架构设计 + 编码 + 验证审查
- 杜赞 (GLM5.2) — 实施方案决策
- Hermes (千问3.7plus) — 协调 + 编码 + bug 修复 + 补齐3 + 铁律8

---

## 一、实施概览

本次实施 M1 文本打通的 4 项前置补齐工作（全部完成）：

| # | 补齐项 | 实施方 | 状态 |
|---|--------|--------|------|
| 1 | neko_launcher_wrapper.py | 实验田维护者 + Hermes | ✅ 完成（含铁律8 overlay） |
| 4 | persona 只读化 | 实验田维护者 | ✅ 完成 |
| 2 | lumo_proxy.py | Hermes | ✅ 完成（含 bug 修复） |
| 3 | lumo_inject_router.py | Hermes | ✅ 完成（M3 注入端点预置） |

---

## 二、改动文件清单

### 新建文件（5 个）

1. **scripts/neko_launcher_wrapper.py** — NEKO 启动 wrapper
   - 移除 memory_server 条目（关闭 NEKO 五维记忆）
   - patch uvicorn.run 拦截 monitor host（0.0.0.0 → 127.0.0.1）
   - 铁律8：注入 lumo provider overlay（monkey-patch api_config_loader.get_config）
   - LUMO_PROXY_TOKEN fail-fast 凭证检查
   - 支持 LUMO_PROXY_BASE_URL 环境变量覆盖端口

2. **apiserver/routes/lumo_proxy.py** — persona-aware OpenAI 兼容端点
   - require_proxy_token 鉴权（hmac.compare_digest 防时序攻击）
   - /persona/v1/chat/completions 端点
   - 人格注入管线（build_system_prompt + message_manager + RAG + build_context_supplement）
   - 旁路 RAG 实现（不碰 chat.py 嵌套函数）
   - 流式 + 非流式 OpenAI 兼容响应
   - reasoning_content 透传

3. **NEKO/N.E.K.O/main_routers/lumo_inject_router.py** — M3 注入端点（补齐3）
   - POST /api/lumo/speak — 注入说话指令（陆墨决策 → NEKO TTS+字幕）
   - POST /api/lumo/emotion — 注入表情切换（复刻 emotion.py 推送格式）
   - require_proxy_token 鉴权
   - 写入 sync_message_queue，经 cross_server 转发给前端

4. **scripts/lumo_provider_overlay.json** — 铁律8 overlay 配置
   - assist_api_providers.lumo: 陆墨人格代理 provider 定义
   - assist_api_key_fields.lumo: LUMO_PROXY_TOKEN 环境变量映射
   - api_key_registry.lumo: 前端配置字段注册

5. **lumo_fusion.ps1** — M1 融合启动脚本
   - 自动生成 LUMO_PROXY_TOKEN（32 字节随机）
   - 启动 scratchpad 后端 → 等待 API 就绪 → 启动 NEKO（wrapper 模式）
   - 可选启动前端和 Neo4j

### 修改文件（3 个）

6. **NEKO/N.E.K.O/main_routers/characters_router/persona.py** — persona 只读化
   - 5 个写端点加 guard 返回 409 + "persona_managed_by_lumo"
   - GET 端点全保留
   - 文件头加 [local-patch] 注释

7. **apiserver/api_server.py** — 路由注册
   - 新增 `from .routes.lumo_proxy import router as lumo_proxy_router`
   - 新增 `app.include_router(lumo_proxy_router)`

8. **NEKO/N.E.K.O/app/main_server/web_app.py** — NEKO 路由注册
   - 新增 `from main_routers.lumo_inject_router import router as lumo_inject_router`
   - 新增 `app.include_router(lumo_inject_router)`（vmc_router 之后、pages_router 之前）

---

## 三、多智能体流程

### 阶段 1: 铁锚确认代码起点
- 确认 17 个代码起点（SERVERS 列表、monitor host、persona 路由、人格注入管线等）
- 识别 7 个风险点（HIGH 3 / MEDIUM 3 / LOW 1）

### 阶段 2: 杜赞 + 实验田维护者讨论方案
- 杜赞决策：_CRITICAL_MODULES 不碰（自然失效）、_query_rag 旁路重写、monitor 用环境变量、补齐3 推迟
- 实验田维护者设计：wrapper monkey-patch 架构、lumo_proxy 接口契约、数据流图

### 阶段 3: 实验田维护者 + Hermes 混合编码
- 实验田维护者实施补齐1（wrapper）+ 补齐4（persona 只读）
- Hermes 实施补齐2（lumo_proxy + api_server 注册）

### 阶段 4: 实验田维护者 + 铁锚验证审查
- 发现 1 个 CRITICAL bug：lumo_proxy.py:211 `multi_agent_context_section=None` 导致 `.strip()` 崩溃
- 发现 3 个 MEDIUM/LOW 问题：reasoning 丢弃、chunk id 不复用、import 路径
- Hermes 修复全部 4 个问题

### 阶段 5: bug 修复
1. **CRITICAL**: `multi_agent_context_section=None` → `""`（build_context_supplement 会 .strip()）
2. **MEDIUM**: 流式响应增加 reasoning chunk 处理（delta.reasoning_content）
3. **LOW**: 流式 chunk id 复用同一 id + created_ts（OpenAI 标准）
4. **MEDIUM**: 非流式响应增加 reasoning_content 字段

---

## 四、验证结果

### 铁锚验证

| 验证项 | 结果 |
|--------|------|
| wrapper SERVERS 过滤逻辑 | ✅ 正确 |
| wrapper sys.path 计算 | ✅ 正确 |
| wrapper start_launcher 调用 | ✅ 正确 |
| persona 5 个写端点 guard | ✅ 全部覆盖 |
| persona GET 端点未修改 | ✅ |
| lumo_proxy hmac.compare_digest | ✅ 防时序攻击 |
| lumo_proxy 路径无冲突 | ✅ /persona/v1/ vs /v1/ |
| lumo_proxy import 签名匹配 | ✅ |
| **lumo_proxy build_context_supplement** | ❌ → ✅ 已修复 |
| 路径冲突检查 | ✅ 无冲突 |
| 安全性检查 | ✅ 通过 |

### 实验田维护者验证

| 验证项 | 结果 |
|--------|------|
| wrapper LUMO_PROXY_TOKEN fail-fast | ✅ |
| wrapper patch 顺序 | ✅ patch 在 start_launcher 前 |
| persona guard 在函数体第一行 | ✅ |
| persona 原代码保留为 unreachable | ✅ 可逆性 |
| lumo_proxy RAG 旁路降级链 | ✅ 失败返回 "" |
| lumo_proxy 保存历史降级链 | ✅ 失败只 warning |
| lumo_proxy 流式异常降级链 | ✅ 发 error delta 后结束 |
| **build_context_supplement 降级链** | ❌ → ✅ 已修复 |

---

## 五、降级链完整性

| 路径 | 降级方式 | 状态 |
|------|----------|------|
| LUMO_PROXY_TOKEN 缺失 | 模块加载 warning → 请求时 503 | ✅ |
| RAG 召回失败 | try/except → 返回 "" → 对话继续 | ✅ |
| 保存对话历史失败 | try/except → warning → 响应继续 | ✅ |
| 流式响应异常 | except → 发 error delta → 结束流 | ✅ |
| monitor host patch 失效 | 子进程不继承 → 降级为不阻塞 | ✅ 已记录 |
| memory_server 移除 | SERVERS 过滤 → _CRITICAL_MODULES 不命中 | ✅ |
| build_context_supplement | 修正 None → "" 后正常 | ✅ 已修复 |

---

## 六、技术债（推迟到 M3 前）

1. ~~**补齐3 lumo_inject_router.py**~~ — ✅ 已完成（M3 注入端点预置，speak/emotion 端点已注册）
2. ~~**NEKO api_providers.json overlay**~~ — ✅ 已完成（铁律8：wrapper monkey-patch get_config 深合并注入）
3. **monitor host 子进程 patch** — 当前 patch 可能不传递到 monitor 独立进程，需验证或改用防火墙规则
4. **_save_conversation_and_logs import 路径** — 当前从 chat.py re-import，建议改为直接从 api_server import
5. **speak 消息类型前端适配** — NEKO 前端 app-websocket.js 需在 M3 阶段新增 `response.type === 'speak'` 分支

---

## 七、M1 文本打通数据流

```
用户 → NEKO 输入框
  → NEKO api_providers.json (lumo provider, overlay 注入)
  → HTTP POST http://127.0.0.1:8000/persona/v1/chat/completions
    Authorization: Bearer $LUMO_PROXY_TOKEN
  → scratchpad lumo_proxy
    1. require_proxy_token 校验
    2. build_system_prompt() — 陆墨人格
    3. message_manager.build_conversation_messages() — session 记忆
    4. _query_rag_standalone() — RAG 召回
    5. build_context_supplement() — 技能+工具+RAG
    6. llm_service.chat_with_context_and_reasoning() — 上游 LLM
  → OpenAI 兼容响应
  → NEKO 显示陆墨回复
```

---

## 八、下一步

1. 运行 `.\lumo_fusion.ps1` 启动融合环境（自动生成 token + 启动后端 + NEKO）
2. 在 NEKO 设置界面选择「陆墨（本地人格代理）」作为辅助 API provider
3. 测试 M1 验证标准：NEKO 输入 → 陆墨人格 + RAG 回复 → NEKO 显示
4. M1 验证通过后进入 M2（语音打通）

---

*报告由 Hermes (千问3.7plus) 协调生成，铁锚 (kimi2.7code) / 实验田维护者 (deepseekv4pro) / 杜赞 (GLM5.2) 并行工作。*
