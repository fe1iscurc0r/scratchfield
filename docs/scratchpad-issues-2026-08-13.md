# scratchpad 问题清单（按点标号）

> 整合来源：08-11 九份模块审计 + 08-13 陆墨全仓审查 + 08-13 沈遥仓库审计
> 状态标注：✅已修 / 🔴高危 / 🟠中 / 🟡低 / ⬜待定
> 日期：2026-08-13

---

## A. 安全止血（第一梯队）

| # | 问题 | 位置 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | route_map.py 明文 Bearer token 已进 git 历史 | `route_map.py` L30-33 | 🔴 | ⬜ 待轮换+清历史 |
| 2 | 08-11 已修 10 项未同步远端 | 本地 vs Gitee 分叉 | 🔴 | ⬜ 待推送 |

## B. 陆墨 5 个新发现（第二梯队）

| # | 问题 | 位置 | 严重度 | 状态 |
|---|---|---|---|---|
| 3 | LLM 驱动裸 shell + set_model 改写 base_url/api_key（提示注入→RCE+密钥外泄） | `agentic_tool_loop.py` | 🔴 | ⬜ |
| 4 | 无鉴权转发真实 api_key（盗刷） | `openai_proxy.py` | 🔴 | ⬜ |
| 5 | 热补丁无校验，.py 优先加载（持久化后门） | `main.py` LUMO_PATCH_DIR | 🔴 | ⬜ |
| 6 | 下载无 SHA-256 + npm @latest 无锁版（供应链） | `build.py` | 🟠 | ⬜ |
| 7 | cancel_task 协程未 await（取消永不生效） | `summer_memory` | 🟡 | ⬜ |

## C. 中危技术债（第三梯队）

| # | 问题 | 位置 | 状态 |
|---|---|---|---|
| 8 | /upload/document 路径穿越 | apiserver | ⬜ |
| 9 | 角色切换路径穿越 | naga_control | ⬜ |
| 10 | MCP 工具读任意文件（~/.ssh/id_rsa） | agentserver | ⬜ |
| 11 | safe-storage 无限制预言机 | frontend | ⬜ |
| 12 | Access Token 明文 localStorage | frontend | ⬜ |
| 13 | Markdown 白名单放行 style（CSS 钓鱼） | frontend | ⬜ |
| 14 | 向量全表加载 15MB/次，sqlite-vec 未启用 | rag | ⬜ |
| 15 | LLM 关系类型直接进 Cypher 写入侧 | rag | ⬜ |
| 16 | openclaw hooks 响应明文返 token | agentserver | ⬜ |
| 17 | 对话内容 INFO 落盘（流式 chunk 全文） | agentserver | ⬜ |
| 18 | WS 无超时永久挂起 | agentserver | ⬜ |
| 19 | 队列满阻塞 + TOCTOU 重复提交 | task_manager | ⬜ |
| 20 | build-win.py 腐坏（引用不存在 spec） | 入口 | ⬜ |
| 21 | 127.0.0.1 被兜底绑 0.0.0.0 | 入口 | ⬜ |

## D. 仓库卫生（沈遥 08-13 审计补充，报告未覆盖）

| # | 问题 | 严重度 | 状态 |
|---|---|---|---|
| 22 | just.png 40MB（8819×5125）误提交 | 🟠 | ⬜ 压缩/删 |
| 23 | knowledge-base 主库/knowledge 仓库重复 | 🟡 | ⬜ 已分库，待确认 |
| 24 | 分支统一 master → main | 🟡 | ⬜ |
| 25 | knowledge 仓库无顶层 .gitignore | 🟡 | ⬜ |
| 26 | 大文件超 50MB 推荐线（xtb 59M 等 10 个） | 🟢 | 可接受 |

---

## 已完成（✅）

- 08-11 九份审计的 10 项高危重合项：**本地已全修**
- 敏感信息扫描：除 #1 外全是占位符/误报，无真实泄露
- .env / 私钥文件：无泄露
- git 历史 token：无真实泄露（ghp_/sk- 均为误报）
