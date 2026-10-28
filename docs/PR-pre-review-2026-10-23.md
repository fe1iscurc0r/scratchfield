# 6 个安全/一致性 PR 预审（2026-10-23）

> 对象：#396 / #397 / #398 / #400 / #401 / #402
> 方式：REST 拉 diff（`/pulls/N/files`）+ 红旗扫描 + 与各单工单点名的目标文件逐个对账 + 冲突面测算
> **性质：只读预审。未合并、未改动任何 PR 分支。**
> ⚠️ 六单的 `statusCheckRollup` **全部 `skipped`**（私有仓无 CI 额度）⇒ **CI 绿灯零信息量**，以下结论全部基于 diff 本身。

---

## §1 结论摘要

| PR | 单 | 规模 | 工单覆盖 | 红旗 | 建议 |
|---|---|---|---|---|---|
| **#396** | WO-268（P0-17 密钥止血） | +649/−61 · 19 文件 | ✅ 命中 | 无 | **可合**（合前人工确认密钥来源已改为强制注入） |
| **#397** | WO-272（P0-18/19 数据丢失） | +1477/−25 · 6 文件 | ✅ 命中 | 🟡 1 处 `except Exception: pass`（通知回调） | **可合**，建议补一行 debug 日志 |
| **#398** | WO-267（P0-1/3/4/5/6 服务边界） | +2551/−33 · 19 文件 | ✅ 命中 | 无（`token="short-token"` 是测试值） | **可合** |
| **#400** | WO-271（P0-12/13/20 文件系统边界） | +954/−20 · 8 文件 | ✅ 三处全命中 | 无（`noqa: F821` 是类型提示） | **可合** |
| **#401** | WO-269（P0-2/7/8 执行面） | +2992/−396 · 20 文件 | ✅ 三处全命中 | 🟡 `pytest.skip` ×5（Windows 符号链接门控） | **可合**（测试是**加强**：删 36 断言/增 83） |
| **#402** | WO-270（P0-9/10/11 前端注入/窗口） | +1378/−42 · 9 文件 | ✅ 命中，但 **P0-10/11 是部分修复** | 🟡 1 处 `skip("node not found")` | **可合但必须改口径**：不能宣称 P0-10/11 已修 |

**冲突面：六个 PR 彼此零文件重叠，且与 main 自基线以来的 25~29 个改动文件零重叠 ⇒ 无冲突面，可任意顺序合并。**

---

## §2 逐单评述

### #396 · WO-268 P0-17 密钥止血

- 覆盖面：`security.py` / `server.py` / `.env.example` / `Dockerfile` / `docker-compose.yml` / `setup.sh` / `README.md`
  + `mirror-gitee.yml` + `WO-268-p0-hmac-secret.md`。**同一批文件名出现两份**（NEKO 侧与 agentserver 侧各一套）——
  与"镜像放大面"这个主题吻合（改一处不够，镜像会继续带旧密钥）。
- 判定：**可合**。合前请人工确认：`.env.example` 里**没有任何真实密钥**，只有占位符。

### #397 · WO-272 P0-18/19 静默数据丢失

- 核心改动（`cross_server.py`）：`chat_history.clear()` + `last_synced_index = 0` 从"无条件执行"改为
  **`if _settle_succeeded:` 才清**；失败走新增的 `memory_settle_retry.py` 待重试队列。这正是 P0-18 的病灶。
- 🟡 **唯一红旗**（新增代码）：

  ```python
  try:
      status_callback(f"⚠️ 有 {exhausted} 条记忆未结算（已自动重试 … 次）")
  except Exception:
      pass
  ```

  位置是**通知回调**，不在数据路径上 ⇒ 不构成数据丢失，**可接受**；但建议加 `logger.debug`，
  否则"用户没收到告警"这件事会无声消失。
- 测试：两个新测试文件均为 **纯新增**（+302/−0、+204/−0），没动既有用例。

### #398 · WO-267 本机服务边界（P0-1/3/4/5/6）

- 覆盖 5 个 P0 项，19 文件，横跨 `main.py` / `agentserver` / `apiserver` / `frontend`，
  两侧各有一份 `net_boundary.py` + `test_net_boundary_policy.py`（**同一张决策表两侧钉**，注释里明说）。
- `token="short-token"` 是测试里的假 token（验证"短 token 被拒"），**不是泄漏**。

### #400 · WO-271 文件系统边界（P0-12/13/20）

- 三个任务点名的目标**全部命中**：`tools/sync_neko_upstream.py`（P0-12）、
  `scripts/sync-to-scratchfield.sh`（P0-13）、`write_main.ps1`/`write_main.js.ps1`/`gen_mainjs.ps1`（P0-20）。
- 新增 `tests/test_sync_neko_upstream_paths.py`（+310），注释点明威胁模型：
  "上游 `/compare` 返回的 `filename` 是**远端可控字符串**"。

### #401 · WO-269 执行面（P0-2/7/8）

- 三处全命中：`mcpserver/code_workspace/sandbox.py`（P0-2）、`app_launcher/__init__.py`（P0-7）、
  `skills/autoskill/scripts/promote.py`（P0-8）。
- **测试是加强不是放宽**（这是本单最容易被误判的地方）：
  `test_code_workspace.py` 删 232 行 / 增 443 行，**删 36 个 assert → 增 83 个**，
  **删 10 个 test 函数 → 增 23 个**。
- 🟡 `pytest.skip` ×5 全在 `test_autoskill_promote_review.py`，条件是
  **"Windows 不给创建符号链接/目录联接点"** ⇒ 属于**平台门控**，不是"用 skip 换绿色"。
  但请确认：在 Linux CI（若有）上这 5 条必须真跑起来（它们验的正是"符号链接逃逸"）。

### #402 · WO-270 P0-9/10/11 —— **只有 P0-9 是完整修复**

- 文件命中 `subscriptions-and-scan.js`（P0-9）+ `window-manager.js` / `preload-jukebox.js` / `pet-window-lifecycle.js`（T2/T3）。
- **但 PR 自己的契约测试注释写明了**：

  > "P0-10/P0-11 的**完整修复**要把 8124 行的 `preload-chat-react.js` 迁到 contextBridge，
  > 那是**独立工程**；本文件先把**已经收敛到的基线钉住**"

- ⇒ 结论：**#402 可合**（它确实收紧了窗口配置并加了防回归契约），但：
  1. **不能**在报告 README 的 P0-10/P0-11 处置列写"已修复"，只能写"**基线锁定 + 部分收敛**"；
  2. 需要单独开一条"contextBridge 迁移"的后续单，否则这两项会被契约测试的绿色**遮住**。
- `eval(`/`exec(` 的命中全是 **JS 正则 `re.exec`** 与"故意构造的危险样本字符串"，**非代码执行**。

---

## §3 合并顺序建议

因六单互不重叠、与 main 也无重叠，**顺序不影响正确性**。建议按"止血优先"排：

| 顺序 | PR | 理由 |
|---|---|---|
| 1 | **#396** | 密钥止血，风险最高、改动最小（+649） |
| 2 | **#397** | 静默数据丢失，影响用户数据 |
| 3 | **#398** | 本机服务边界（对外暴露面） |
| 4 | **#400** | 文件系统边界 |
| 5 | **#401** | 执行面（改动最大 +2992，测试同步加强，最需要人工看） |
| 6 | **#402** | 前端/Electron（含"部分修复"口径问题，最后合并同步改口径） |

---

## §4 必须人工确认的 5 件事（CI 帮不了）

1. **#396**：`.env.example` 与 `README` 里不得残留任何真实密钥/真实 token。
2. **#398**：两侧 `net_boundary.py` 的**决策表必须逐行一致**（PR 用两份测试钉同一张表，
   但请人眼对一遍：默认拒绝还是默认放行）。
3. **#401**：`test_code_workspace.py` 新增的 23 个用例里，是否**每个都真有断言**（不是"跑了就算"）。
4. **#402**：报告 README 的 P0-10/11 处置列改成「基线锁定/部分收敛」，并**新开一条** contextBridge 迁移单。
5. **#397**：`except Exception: pass` 建议补 `logger.debug`（属建议，不阻塞）。

---

## §5 复现命令

```bash
# 概览
curl -s -H "Authorization: Bearer $PAT" \
  https://api.github.com/repos/fe1iscurc0r/scratchpad/pulls/396 | jq '{additions,deletions,mergeable}'

# 逐文件 diff（含 patch）
curl -s -H "Authorization: Bearer $PAT" \
  "https://api.github.com/repos/fe1iscurc0r/scratchpad/pulls/398/files?per_page=100"

# 冲突面：PR 基线之后 main 改过哪些文件
curl -s -H "Authorization: Bearer $PAT" \
  "https://api.github.com/repos/fe1iscurc0r/scratchpad/compare/<base_sha>...main" | jq '.files[].filename'
```

> 本地留档：`_prs.json`（六单完整 diff 快照，764 KB，含每文件 patch）。

---

## §6 预审没有做的事

- **没有合并任何 PR**，也没有往分支推东西。
- **没有在本地跑这六个 PR 的测试**（要 checkout 六条分支并装 NEKO 依赖；CI 又全 skipped）。
  ⇒ 若要把"可合"变成"已验证"，下一步是逐条 `git checkout` + 本地 `pytest`，我可以按上面的顺序做。
- 没有评价代码风格/命名，只看**功能覆盖与红旗**。
