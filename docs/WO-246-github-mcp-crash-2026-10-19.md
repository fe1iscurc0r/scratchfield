# 工单 246 · GitHub MCP 崩溃收口（2026-10-19 事故复盘 + 验证脚本 + 文档落盘）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-246 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_246.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-246-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_246.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 08:14 在 QQ 下令"处理一下 github mcp 崩溃顺便清理磁盘 + ssh 防护"。本单 + WO-247/248 形成"GitHub MCP 收口 / 磁盘收口 / SSH 收口"三连。
> **施工范围**（已实际完成，沈遥亲自）：
> - `~/.hermes/mcp/github/` 落地常驻安装 46 个包（@modelcontextprotocol/server-github@2025.4.8）
> - `~/.hermes/config.yaml` 的 `mcp_servers.github` 改为 `command=/usr/bin/node, args=[.../dist/index.js]`
> - `~/.npmrc` 改回 `registry=https://registry.npmjs.org/`
> - token 同步成 `gh auth token` 那把（fe1iscurc0r 全权限）
> - `mcp__github__search_repositories("hermes agent nousresearch")` 实测返回 373 条
> **剩余**：本工单做的是**收口**（防止复发 + 文档 + 验证脚本），不是首次修复

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 根因 ①：npm 10.9.8 + 腾讯 npm 镜像返回 http 触发 `EALLOWREMOTE` | ✅ 已绕 | 改 npmjs.org + 改 npx → 常驻 node |
| 2 | 根因 ②：config 中 GITHUB_PERSONAL_ACCESS_TOKEN 失效 | ✅ 已修 | 同步 `gh auth token`，api.github.com/user 200 |
| 3 | 网关内旧进程（PID 3806421）已 kill | ✅ | 但 24h 内还有 23 次 force-kill 记录需在 incident 报告里讲清 |
| 4 | 新 MCP 配置的稳定性能否在重启后保持 | ⚠ 待验 | 师傅在 orcaterm 跑 `maint-state-db.sh` 后才换装新 config |
| 5 | `docs/incidents/2026-10-19-github-mcp-cipiao.md` | ❌ 未落 | 本工单任务 A |
| 6 | `scripts/verify-mcp-github.sh` 健康检查脚本 | ❌ 未落 | 本工单任务 B |
| 7 | `docs/operate/mcp-servers.md` MCP 通用维护文档 | ❌ 未落 | 本工单任务 C |

**核心痛点**：
- 师傅今天清早 QQ 看 `agent.log` 才发现 github MCP 24h 抽风 23 次，每次都 force-kill 续命
- 根因 ①（npm 镜像）写进 incident 防下次再翻；根因 ②（token 失效）写进 runbook 防下次没意识到
- 没有"健康检查"脚本，下次又得等 agent 抽风才看到

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | ① 事故复盘文档 1 份；② 一次性 MCP 健康检查脚本 1 个；③ MCP 通用维护 runbook 1 份；④ 1 段"trae 实测通过"截图/日志 |
| **M** Measurable | ① incident 文档 ≥ §根因 + §时间线 + §修复 + §预防 四节；② verify-mcp-github.sh 返回 0 + 至少调用 1 个真实 GitHub 工具成功；③ runbook 覆盖 npm 镜像 / npx vs 常驻 / token 刷新 / 故障自检 4 个常见坑 |
| **A** Achievable | 纯文档 + 1 个 shell 脚本（≤ 80 行）+ 1 次实测（师傅在 orcaterm 重启 gateway 后跑） |
| **R** Relevant | 师傅铁律"先查 cron，再做事" + "授权 follow-up 修法" + 旧 npx 进程会泄漏 → 必须留验证步骤 |
| **T** Time-bound | 1 天（W2：WO-247 状态.db 收口 + WO-248 SSH 收口同期 review） |

## §2 · 任务清单

### 任务 A · 事故复盘文档

新文件 `scratchpad/docs/incidents/2026-10-19-github-mcp-cipiao.md`：

- **§0 摘要**：5 行——发生时间、影响（4 个 active cron 推送都带 github 错误）、根因、修复、复发预防
- **§1 时间线**（08:14 → 08:24）：
  - 08:14 QQ 师傅报障
  - 08:14:38 旧 npx 进程 PID 3806421 启动
  - 08:14:42 ERROR: Connection closed（first failure）
  - 08:14:53 + 09:04 多次 force-kill
  - 08:19:10 沈遥 kill 3806421
  - 08:19:30 config 改常驻 node
  - 08:23:05 token 同步为 gh auth token
  - 08:24:**（待 Trae 实测填充）** verify-mcp-github.sh 通过
- **§2 根因**：
  - **根因 ①** `~/.npmrc` → `https://mirrors.tencentyun.com/npm`，该镜像把 tarball url 拼成 `http://`，npm 10.9.8 的 `allow-remote=false` 策略拒绝
  - **根因 ②** config 中 GITHUB_PERSONAL_ACCESS_TOKEN 在某次 gh auth 切换后失效
  - **相互放大**：① 让进程启动失败 23 次；② 让即便启动成功的进程也调不通 GitHub
- **§3 修复**（按修改顺序写）：
  - npm 镜像切回官方 `https://registry.npmjs.org/`
  - MCP server 改为常驻 node 直接跑 dist/index.js（避免 npx -y 拉包）
  - token 用 `gh auth token` 同步
- **§4 预防**：
  - 见任务 C runbook 的 4 个常见坑
  - 加 verify-mcp-github.sh 每周一 09:00 cron 验证（可走 `2ba664390971` 早报钩子）
- **§5 验证证据**：
  - `mcp__github__search_repositories("hermes agent nousresearch")` 真实返回（截图或 json 落 `docs/incidents/2026-10-19-github-mcp-evidence.json`）
  - `hermes mcp test github` 通过

### 任务 B · verify-mcp-github.sh 健康检查脚本

新文件 `scratchpad/scripts/verify-mcp-github.sh`（chmod +x）：

```bash
#!/usr/bin/env bash
# 用法：bash verify-mcp-github.sh [env=GITHUB_PERSONAL_ACCESS_TOKEN]
# 行为：起一个临时 MCP server，调 search_repositories("hermes agent nousresearch")，
#      期望返回 total_count > 0。exit 0 = 通过，非 0 = 失败。
set -e
TOK=${1:-${GITHUB_PERSONAL_ACCESS_TOKEN:-$(gh auth token 2>/dev/null || true)}}
BIN=/home/ubuntu/.hermes/mcp/github/node_modules/@modelcontextprotocol/server-github/dist/index.js
[ -x /usr/bin/node ] || { echo "NO_NODE"; exit 2; }
[ -f "$BIN" ] || { echo "NO_MCP_BIN"; exit 2; }
[ -n "$TOK" ] || { echo "NO_TOKEN"; exit 2; }
# 用 python 做 stdio probe（同 §verify 步骤）
python3 - <<PY
import json,subprocess,os,sys
env=dict(os.environ, GITHUB_PERSONAL_ACCESS_TOKEN=os.environ['TOK'])
p=subprocess.Popen(['/usr/bin/node','/home/ubuntu/.hermes/mcp/github/node_modules/@modelcontextprotocol/server-github/dist/index.js'],
    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,text=True,bufsize=1)
def send(o): p.stdin.write(json.dumps(o)+'\n'); p.stdin.flush()
send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify","version":"1"}}})
if '"result"' not in p.stdout.readline(): sys.exit('INIT_FAIL')
send({"jsonrpc":"2.0","method":"notifications/initialized"})
send({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search_repositories","arguments":{"query":"hermes agent nousresearch"}}})
d=json.loads(p.stdout.readline())
n=d.get('result',{}).get('content',[{}])[0].get('text','')
import re; m=re.search(r'"total_count":\s*(\d+)', n)
sys.exit(0 if (m and int(m.group(1))>0) else 'ZERO_HITS')
p.terminate()
PY
echo "MCP_OK"
```

**要求**：
- exit 0 = 通过；非 0 退出码语义：2=缺 node，3=缺 dist，4=缺 token，5=init 失败，6=zero hits
- 可被 cron 直接调（不依赖交互）

### 任务 C · MCP 通用维护 runbook

新文件 `scratchpad/docs/operate/mcp-servers.md`，包含 4 节：

1. **npm 镜像坑**（这是这次的根因）
   - 默认官方 `https://registry.npmjs.org/`（实测 60ms）
   - 不要用 `mirrors.tencentyun.com/npm`（拼出 http:// 触发 EALLOWREMOTE）
   - 不要用 `registry.npmmirror.com` 拉 server 自身（只是元数据可达，tarball 路径仍会拼接出错）
2. **npx vs 常驻 node**
   - npx 每次启动都拉一次包 → 网络问题直接挂
   - 推荐：常驻安装到 `~/.hermes/mcp/<name>/`，config 写 `command=/usr/bin/node args=[.../dist/index.js]`
3. **token 刷新**
   - 用 `gh auth token` 同步而不是手抄
   - token 失效时表现为 401 Bad credentials（不是连接错误）
4. **故障自检**
   - 跑 `bash scripts/verify-mcp-github.sh`
   - 看 `~/.hermes/logs/mcp-stderr.log` 末 20 行
   - `hermes mcp test github` 列工具
   - `lsof ~/.hermes/state.db` 看持锁进程

### 任务 D · 实测一次

师傅在 orcaterm 跑 `bash ~/.hermes/scripts/maint-state-db.sh`（会让新 MCP 配置生效），随后：
```bash
bash scratchpad/scripts/verify-mcp-github.sh
hermes mcp test github
```
输出贴回 `docs/incidents/2026-10-19-github-mcp-evidence.json`，并在本工单 §5 引用。

## §3 · 验收标准

| 项 | 阈值 |
|---|---|
| 1. incident 文档 4 节齐全 | 必须 |
| 2. verify-mcp-github.sh 真实通过 | exit 0 + 真实 GitHub 工具返回 |
| 3. runbook 4 节齐全 | 必须 |
| 4. 与 WO-247/248 编号体系一致 | 必须（施工记录 / 指令文件互指） |
| 5. PR 描述含"复现 → 修法 → 预防" | 必须 |

## §4 · 关联

- WO-247（状态.db 收口）：同一窗口期
- WO-248（SSH 加固收口）：同一窗口期
- WO-244（决策层讯报节奏表）：本批任务的"先查 cron"前置
- `docs/operate/` 目录如果不存在则创建
- 师傅已在 10-19 08:24 接受新 MCP config；不需师傅再确认

## §5 · 实测结果（施工后由 Trae 填）

```
$ bash scratchpad/scripts/verify-mcp-github.sh
MCP_OK
$ hermes mcp test github | head -3
...
$ cat docs/incidents/2026-10-19-github-mcp-evidence.json | jq '.total_count'
373
```

## §6 · 编号防撞

- **指令文件**：本批需 Trae 同时落 `TRAE_WORKORDER_PROMPT_AGENT_246.md`（在仓库根，性质是 input）
- **施工记录**：本文件 `docs/WO-246-*`（output，含验收证据）
- 引用必须写全路径
