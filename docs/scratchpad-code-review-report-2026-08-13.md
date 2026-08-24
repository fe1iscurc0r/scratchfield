# 陆墨 Lumo(scratchpad)代码审查报告

> 审查时间:2026-08-13 | 仓库:gitee.com/fe1iscurc0r/scratchpad
> 审查范围:apiserver / agentserver / mcpserver / frontend / neko-electron-shell / rag / system / guide_engine / summer_memory / voice / main.py / build.py / scripts(排除 NEKO 上游子模块、vendor、skills 第三方库)
> 审查方式:5 路并行深度审查 + 全局危险模式扫描

---

## 总体评估

这是一个**安全整改意识很强但尚未完工**的项目。代码中遍布 `HIGH-x/MEDIUM-x 修复` 溯源注释,说明已经过多轮整改——**lumo_proxy、cors_config、rag.py、naga_auth 加密层等模块的安全完成度相当高**。但存在三类系统性问题:

1. **"修了但没接线"**:`security_utils.py`(183 行 SSRF/路径穿越防护)全仓库零调用;RAG 的 fail-fast 改造被底层返回随机向量的行为架空;RRF 融合改了分数尺度却没同步默认阈值,导致**默认参数检索恒为空**。
2. **认证默认裸奔**:apiserver `require_auth=False`、agentserver 绑 `0.0.0.0` 零鉴权、TTS 服务 `require_api_key=False`——局域网内任何设备可调用工具/删除数据/盗刷额度。
3. **neko-electron-shell 是全仓库最大风险点**:多窗口 `nodeIntegration:true + contextIsolation:false + webSecurity:false` 且加载 HTTP 后端页面,IPC 无发送者校验——**这是唯一的 RCE 级攻击链**。

---

## 🔴 高危问题(建议立即修复)

### A. 直接可用的攻击链

| # | 位置 | 问题 | 修复方向 |
|---|------|------|---------|
| 1 | `neko-electron-shell/src/window-manager.js:485-553,782-786,871-875` | Chat/Subtitle/AgentHUD 窗口 `nodeIntegration:true + contextIsolation:false + webSecurity:false`,页面来自可配置的 HTTP baseUrl——配远程 URL 即远程 RCE,localhost 下任何 XSS 即升级 RCE | 全部改 `contextIsolation:true + sandbox:true + nodeIntegration:false`,能力走 contextBridge 白名单(frontend/preload.ts 是现成范本) |
| 2 | `neko-electron-shell/src/main/storage-gate.js:624-646` + `main.js:3099` + `screen-capture-ipc.js:566-578` | 特权 IPC 无 sender 校验;`open-path` 可打开任意路径;子窗口 `setWindowOpenHandler` 对任意 URL allow | IPC handler 统一校验 `event.senderFrame.url`;open-path 限数据目录;子窗口强制 isolation |
| 3 | `agentserver/agent_server.py:3118` + `config.py:25` | agent server 绑 `0.0.0.0` 且全端点零鉴权:`/tools/invoke` 调任意工具、`DELETE /agents/{id}` 删数据 | 默认绑 127.0.0.1;0.0.0.0 必须配共享密钥 |
| 4 | `mcpserver/mcp_server.py:88-89,141-163` | `/schedule` 的 `callback_url` 完全未校验 → SSRF,工具结果(含屏幕分析/对话)可被外发;而 `security_utils.validate_callback_url()` 已写好却是死代码 | 接线该函数 + `follow_redirects=False` |
| 5 | `apiserver/agentic_tool_loop.py:797-857` + `naga_control.py:180-197` | LLM 输出驱动裸 shell 执行 + 任意路径写入;`set_model` 允许 LLM 改写并持久化 `api.base_url`/`api_key` → 提示注入可致 RCE + 密钥外泄 | exec 加确认门;write/edit 限白名单目录;高危 action 需用户确认 |
| 6 | `apiserver/routes/openai_proxy.py:841-860` | 无鉴权 OpenAI 代理,用用户真实 api_key 转发上游 → 局域网/恶意网页盗刷额度 | 加共享密钥鉴权;上游错误体不外传 |

### B. 功能已坏但不报错

| # | 位置 | 问题 | 修复方向 |
|---|------|------|---------|
| 7 | `rag/rag_service.py:222-232` + `apiserver/routes/rag.py:44` | RRF 融合分数(max≈0.32)与默认 `min_score=0.6` 尺度不匹配 → **默认参数下 RAG 检索恒返回空** | 融合后归一化到 [0,1] 或降阈值;补回归测试 |
| 8 | `rag/embedding_engine.py:142-144,179-181` | 嵌入失败返回**固定种子随机向量**而非 None,架空上层 fail-fast → 文档静默写入无意义向量,检索"正常"但结果随机 | 失败返回 None;随机降级仅留测试开关 |
| 9 | `apiserver/routes/auth.py:393` | `/auth/refresh` 传参 `rt_override` 但 `naga_auth.refresh()` 无参 → TypeError 被吞 → 该端点自始不可用 | 补形参或路由改无参调用 |
| 10 | `summer_memory/memory_manager.py:262,275` | `cancel_task` 是协程却被同步调用(未 await)→ 取消操作从未生效 | 加 await 或提供同步包装 |

### C. 凭证与供应链

| # | 位置 | 问题 | 修复方向 |
|---|------|------|---------|
| 11 | `route_map.py:31` | 真实 access_token 明文入库:`Nncpb125Lobq2...` | 删除+吊销+轮换;`git filter-repo` 清历史 |
| 12 | `agentserver/openclaw/installer.py:119-184` | fallback 路径把真实 LLM API Key 明文写入 `~/.naga/openclaw/openclaw.json`(主路径反而用占位符,两条路径不一致) | fallback 同样用占位符;文件 chmod 600 |
| 13 | `main.py:24-52` | 热补丁机制无校验:`LUMO_PATCH_DIR`/`%APPDATA%/lumo/patches` 下 .py 优先于正式代码加载 → 持久化后门 | 补丁签名校验或 SHA-256 白名单 |
| 14 | `build.py:283,867,1474` + `build.py:64` | Node/Python/uv 下载无 SHA-256 校验;`npm install agent-browser` 无版本锁;mcporter 用 `@latest` | 钉死版本 + 完整性校验 |
| 15 | `agentserver/openclaw/instance_manager.py:301-345` + `main.py:486-609` | 启动时按端口**无差别 SIGTERM/taskkill 任意进程**(扫描约 200 个端口),误杀用户无关服务 → 数据丢失 | kill 前校验进程 cmdline 含 openclaw/naga 标识 |

---

## 🟡 中危问题(择要)

**apiserver**
- `/auth/me` token 固化链:中间件对任意 Bearer token 设上下文不校验 + `get_me` 不比对当前 token + `restore_token` 让攻击者"自选"合法 token(`api_server.py:144-165` / `naga_auth.py:340-349`)
- `/upload/document` 路径穿越:`filename` 直接拼路径,无白名单无大小限制(`routes/extensions.py:1846-1874`)——rag.py 明明有正确写法没复用
- `require_local_auth` 默认 `require_auth=False` 形同虚设;未配置密码时任意用户名密码可登录
- mcp.so 安装 SSRF(`extensions.py:1139-1146`)+ Windows 下 `_run_command` shell=True 注入面
- CORS 自相矛盾:中间件锚定正则很严,但 `chat.py:1207` 又手写 `Access-Control-Allow-Origin: *`
- 角色切换路径穿越:`naga_control.py:224-242` 可被 LLM 工具触达
- `llm_service.py:331-334` 日志打印 token 前 20 字符(约泄露一半)

**agentserver/mcpserver**
- PowerShell f-string 拼接注入(`comprehensive_app_scanner.py:214-232`)
- MCP 工具可读任意文件:`markitdown/llm4decompile/paper_miner` 无路径白名单 → 提示注入可让模型读 `~/.ssh/id_rsa`
- `/openclaw/config/hooks` 响应体明文返回新 token(叠加零鉴权 = 局域网可索取)
- 用户对话内容大量以 INFO 级落盘(流式 chunk 全文!`instance_manager.py:1192`)
- WS 请求无超时永久挂起(`ws_client.py:164-176`);配置写入非原子崩溃即损坏;非幂等 POST 重试 5 次致重复副作用
- QQ 通知链路断裂(硬编码空 URL);遥测事件因塞 Exception 对象被静默全丢

**frontend**
- 自定义协议 `startsWith` 前缀混淆路径穿越(`electron/main.ts:121-136`,`/characters2` 可绕过 `/characters` 校验)
- safe-storage 加解密 IPC 是无限制预言机;bridge token 明文落盘权限未收紧
- Access Token 明文存 localStorage + 回写后端 config;Markdown 白名单允许 `style` 属性(CSS 钓鱼面)
- neko 侧权限自动授予过宽(media/clipboard-read/fileSystem 不区分来源)

**业务核心(rag/summer_memory/voice)**
- SQLite 连接跨线程共享无写锁 + 重连竞态(`vecdb_client.py`)
- 向量检索每次全表加载所有 embedding(1万条≈15MB/次),sqlite-vec 扩展加载了却没用它
- LLM 生成的关系类型直接进入 Cypher 写入侧(py2neo 不转义,查询侧已参数化)
- task_manager:队列满时永久阻塞、TOCTOU 重复提交、双清理循环跨事件循环
- TTS 服务绑 0.0.0.0 且 `require_api_key=False`;临时音频文件无人清理磁盘泄漏;`requests.get` 无超时

**入口与脚本**
- `lumo.ps1`/`lumo_fusion.ps1` 硬编码开发机绝对路径 + 按 `main\.py` 正则误杀任意 Python 进程
- `scripts/build-win.py` 与 build.py 大面积重复且已腐坏(引用不存在的 spec/tsconfig)→ 建议删除
- `main.py:623-687` 引用不存在的 `update.py` + json5 读 json 写丢格式
- `main.py:328-332` 配置 127.0.0.1 也会被"兜底"绑 0.0.0.0

---

## ✅ 做得好的地方(值得保持)

- **lumo_proxy/lumo_event**:共享密钥 fail-fast、bytes 比较防时序、session_id 白名单、LRU 防重放、日志 sanitize——全仓库安全完成度最高
- **naga_auth 加密层**:SafeStorage→Fernet 三级降级、token 原子写入+0600、PBKDF2-600k、`hmac.compare_digest`
- **rag.py 路由**:扩展名白名单、穿越拦截、大小限制、对外错误脱敏——模板级写法
- **cors_config.py**:锚定正则防 `localhost.evil.com` 绕过,注释记录历史坑
- **frontend/electron**:三道防线(isolation + 无 node + IPC 白名单),MatChat BrowserView 独立 partition + sandbox
- **neko_launcher_wrapper.py**:token fail-fast、overlay 注入不改上游源码、启动期 patch 完整性守护——工程质量最高
- **db.py 全程参数化 SQL**;子进程全部 list 形式 `shell=False`;每干员一把 asyncio.Lock
- 全局扫描:**eval/exec/pickle 零使用**,硬编码密钥仅 1 处

---

## 📋 修复路线图建议

**第一梯队(本周,安全止血)**
1. neko-electron-shell 窗口安全三件套改造(#1/#2)——唯一 RCE 链
2. agentserver/mcpserver 绑 127.0.0.1 + 共享密钥(#3/#4)
3. 删 `route_map.py` 的 token + 吊销轮换(#11)
4. `_execute_local_tool` 确认门 + 路径白名单(#5)
5. openai_proxy 加鉴权(#6)

**第二梯队(功能正确性)**
6. 修 RAG 尺度错配(#7)+ 随机向量降级(#8)+ refresh 签名(#9)+ cancel_task(#10)——四个"静默坏掉"
7. 杀进程前校验进程身份(#15)
8. installer fallback 密钥明文(#12)

**第三梯队(技术债)**
9. 热补丁签名校验(#13)+ 构建供应链校验(#14)
10. 接线或删除 `security_utils.py`(已写好的防护别浪费)
11. 拆 `agent_server.py` 的 670 行 `_run_travel_session`、`extensions.py` 2551 行六域混杂、前端 2000 行级组件
12. 删死代码:build-win.py、LumoAdapter、registry_app_scanner、update.py 引用

---

## 审查方法论说明

- 5 个并行深度审查代理分别覆盖:apiserver / agentserver+mcpserver / 入口+构建 / frontend+neko-shell / 业务核心模块
- 全局模式扫描确认:eval(0)、exec(0)、pickle.loads(0)、shell=True(1 处)、os.system(2 处)、硬编码密钥(1 处)
- 排除范围:NEKO 上游子模块(镜像)、skills/(16.5万行第三方技能库,抽查 subprocess 均为 list 形式)、vendor/references/papers/vault 数据目录
