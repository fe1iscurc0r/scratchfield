# scratchpad 安全审计整合台账

> 整合: 08-11 九份模块审计 + 08-13 陆墨全仓库深度审查
> 目的: 去重 + 标注修复状态 + 统一待办
> 日期: 2026-08-13

---

## 状态速览

| 层 | 状态 |
|---|---|
| 本地库 | ✅ 08-11 九份报告问题**已全修** |
| 远端 Gitee/云服 | ❌ 0 同步，还是旧代码 |
| 陆墨 08-13 高危 | 15 项 = 10 重合(本地已修) + **5 新发现(已修 2026-08-17)** |

---

## 一、高危整合（15 项）

### 重合（10 项，本地已修，远端待同步）

| # | 问题 | 旧报告来源 |
|---|------|-----------|
| 1 | neko-shell 窗口 nodeIntegration+contextIsolation:false → RCE | neko C1 |
| 2 | neko-shell IPC 无 sender 校验 + open-path 任意路径 | neko H2/M2 |
| 3 | agentserver 绑 0.0.0.0 零鉴权 | agentserver C1 |
| 4 | mcpserver /schedule callback_url SSRF | mcpserver H1 |
| 7 | RAG RRF 分数尺度错配 → 恒空 | guide-rag C1 |
| 8 | 嵌入失败随机向量架空 fail-fast | guide-rag H1 |
| 9 | /auth/refresh 签名不匹配 | apiserver H1 |
| 11 | route_map.py token 明文 | scratchpad-repo H1 |
| 12 | installer fallback 密钥明文 | agentserver H1 |
| 15 | 杀进程无差别 SIGTERM | agentserver M1(升级) |

### 🆕 新发现（5 项，本地已修 2026-08-17，commit b2977eb60）

| # | 问题 | 严重度 | 修复状态 |
|---|------|--------|---------|
| 5 | `agentic_tool_loop.py` LLM 驱动裸 shell + `set_model` 改写 base_url/api_key | 🔴 提示注入→RCE+密钥外泄 | ✅ 已修：exec 命令白名单(_EXEC_SAFE_COMMANDS)+shell 元字符过滤；set_model 移除 base_url/api_key 改写 |
| 6 | `openai_proxy.py` 无鉴权转发真实 api_key | 🔴 盗刷 | ✅ 已修：/v1/chat/completions 加 require_local_origin（仅本机回环 + 登录态） |
| 10 | `summer_memory` cancel_task 协程未 await | 🟡 取消永不生效 | ✅ 已修：cancel_task 改 async 并补 await；clear_memory 补 await |
| 13 | `main.py` 热补丁无校验(LUMO_PATCH_DIR .py 优先加载) | 🔴 持久化后门 | ✅ 已修：加载前 Ed25519 签名 + SHA-256 校验；新增 --sign-patch 工具 |
| 14 | `build.py` 下载无 SHA-256 + npm @latest 无锁版 | 🟠 供应链 | ✅ 已修：agent-browser 锁 @0.34.0；下载后 _verify_archive_sha256 校验权威哈希 |

---

## 二、中危整合（去重后）

| 模块 | 问题 | 重合旧报告 |
|------|------|-----------|
| apiserver | CORS 手写 `*`(chat.py:1207) | ✅ M2 |
| apiserver | llm_service 日志泄 token 前 20 字符 | ✅ L1 |
| apiserver | /auth/me token 固化链 | ✅ C1 |
| apiserver | /upload/document 路径穿越 | 🆕 |
| apiserver | require_local_auth 默认 False 形同虚设 | ◐ |
| apiserver | mcp.so 安装 SSRF + Windows shell=True | ◐ |
| apiserver | 角色切换路径穿越(naga_control) | 🆕 |
| mcpserver | PowerShell f-string 注入 | ✅ M1 |
| agentserver | MCP 工具读任意文件(~/.ssh/id_rsa) | 🆕 |
| agentserver | openclaw hooks 响应明文返 token | 🆕 |
| agentserver | 对话内容 INFO 落盘(流式 chunk 全文) | 🆕 |
| agentserver | WS 无超时永久挂起 | 🆕 |
| agentserver | QQ 通知链路断裂 | ✅ H2 |
| frontend | 自定义协议 startsWith 前缀混淆 | 🆕 |
| frontend | safe-storage 无限制预言机 | 🆕 |
| frontend | Access Token 明文 localStorage | 🆕 |
| frontend | Markdown 白名单放行 style(CSS 钓鱼) | 🆕 |
| frontend | neko 权限自动授予过宽 | ✅ neko M1 |
| rag | SQLite 跨线程共享无写锁 | ✅ M5 |
| rag | 向量全表加载 15MB/次,sqlite-vec 没启用 | 🆕 |
| rag | LLM 关系类型直接进 Cypher 写入侧 | 🆕 |
| task_manager | 队列满阻塞 + TOCTOU 重复提交 | ◐ |
| voice | TTS 绑 0.0.0.0 + require_api_key=False | ✅ H1 |
| voice | 临时音频无人清理 | ✅ H2 |
| voice | requests.get 无超时 | ✅ M4 |
| 入口 | lumo.ps1 硬编码绝对路径 + 误杀 | ◐ |
| 入口 | build-win.py 腐坏(引用不存在 spec) | 🆕 |
| 入口 | update.py 不存在 | ✅ H2 |
| 入口 | 127.0.0.1 被兜底绑 0.0.0.0 | 🆕 |

---

## 三、陆墨新报告增量价值

1. **5 项新发现高危**（#5/#6/#10/#13/#14），其中 #5/#6 是提示注入直达 RCE+盗刷的新攻击面，#13 是后门级
2. **系统性三问题提炼**："修了但没接线"(security_utils 零调用)、"认证默认裸奔"、"neko-shell 唯一 RCE 链"
3. **覆盖盲区补齐**：把裸 shell/exec/热补丁这类跨模块攻击面单独扫描

## 四、做得好（保持）

lumo_proxy/lumo_event 共享密钥 fail-fast、naga_auth 加密层(SafeStorage→Fernet 三级)、rag.py 路由模板级写法、cors_config 锚定正则、frontend/electron 三道防线、neko_launcher_wrapper token fail-fast、db.py 全参数化、全局 eval/exec/pickle 零使用。

---

## 五、统一待办（按优先级）

### 第一梯队（止血，远端立即）
1. **token 轮换**：route_map.py 明文 token 已在 Gitee 历史(route_map.py + 审计报告两处) → 吊销 + git filter-repo 清历史
2. **同步本地修复**：本地 `git pull --rebase origin master` → `git push`（把 08-11 全修 + docs 合并）

### 第二梯队（补陆墨 5 新发现）
3. #5 agentic_tool_loop exec 确认门 + set_model 白名单
4. #6 openai_proxy 加共享密钥鉴权
5. #13 热补丁签名校验 / SHA-256 白名单
6. #14 build.py 钉版本 + 完整性校验
7. #10 cancel_task 补 await

### 第三梯队（中危 🆕 项）
8. 路径穿越类(/upload/document、角色切换)、MCP 工具读任意文件白名单、safe-storage 预言机、Access Token localStorage、热补丁之外的技术债

---

## 元记录

- 关联: 08-11 九份 audit + 08-13 陆墨 code-review-report
- 根因: 08-11 按模块零散审计 + 定性标准不统一(openai_proxy 被降级 LOW)，陆墨 5 路并行+全局扫描补齐
- 教训: 不能因上轮审过就默认安全，外来代码每轮重过，定性不降级
