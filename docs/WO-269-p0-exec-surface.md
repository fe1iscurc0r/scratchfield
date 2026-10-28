# 工单 269 · P0 执行面：环境泄漏、无确认门的自启、无审查的技能转正

> ⚠️ **编号体系**：本文件是**施工记录**。指令原文是 `TRAE_WORKORDER_PROMPT_AGENT_269.md`（派单表 `P0-派单表-2026-10-22.md` 第三波）。
> 委托方：用户 · 执行：Qoder · 出单：沈遥 · 日期：2026-10-22
> **定罪基线**：`main@61835ad63625b6777ec880554536a87b8d46848c`
> **交付分支**：`wo/269-p0-exec-surface`（不动 `main`；PR 见文末）
> **本机等价关系**：本地代码树在 `D:\my git\scratchpad-unified`，其一层对应远端仓根。下文所有远端路径按远端写法（不带 `scratchpad-unified/` 前缀）。工作区是 CRLF，仓库存 LF，交付时按 LF 归一。

---

## §0 一句话结论

「模型/外部内容 → 本机执行」这条链上三个没有闸门的位置，各加了一道**在副作用发生之前**就停下来的门，每道门都有"改坏必然红"的变异对照背书：

| 项 | 病灶 | 收口方式 | 反证实验 |
|---|---|---|---|
| P0-2 | `sandbox.py:251` `env = {**os.environ, ...}` ⇒ 模型写的代码片段继承**全部**环境变量（各厂商 API key/token 都在里面）；`:339` 直接 `sys.executable -c`，无解释器隔离 | `ENV_ALLOWLIST` 白名单 + `_SECRET_NAME_RE` 名字黑名单（命中即永不透传）+ `ENV_FORCED_DEFAULTS` 主动设定 + `-I -E -B -X utf8`；cwd 固定沙箱根 | 8 条变异全被抓；A/B：同一份探针跑父进程带 `OPENAI_API_KEY=leak-canary`，子进程读到 `None`、`PATH` 仍可见、`sys.flags.isolated=1` |
| P0-7 | `app_launcher` 三步（`add_app` / `launch_app` / `set_autostart`）都是模型可直接调用的 plugin entry：一次调用就能往 `HKCU\...\Run` 写"开机即执行"的命令，路径不校验、不确认 | **两层门**：入口退出自动路由（`metadata.agent_auto=False`）+ 函数级一次性确认令牌（TTL 300s、指纹绑定 `app_id`+`command`、绑会话、pop-before-validate）；令牌不进 `llm_result_fields`；登记时校验存在性/绝对路径/UNC/`..`/扩展名白名单；落盘前把完整 command 打进日志 | 10 条变异全被抓（见 §2.7，其中 M7 抓出一条**假绿**测试并已重写）；`SetValueEx` 未被调用 + 返回体含确认要求 = 工单验收原文 |
| P0-8 | `skills/autoskill/scripts/promote.py:31` `shutil.move` 前只看源在不在、目标在不在，**不看内容**；上游是"屏幕采集 → LLM 生成"的产物 | 转正前跑一次静态审查（AST 两张危险表 + 11 条命名正则 + 越界链接检测），命中即 `rc 2` 拒；唯一出口是人读完再带**内容寻址摘要** `--approve-reviewed <sha>`；默认 dry-run，`--apply` 才动文件；判定只住 `_refused()` 一处 | 11 条变异全被抓（见 §3.6，其中两条抓出**我自己的**问题：`-X utf-8` 被 Python 静默忽略导致乱码误判、审查判定被抄成两份）；3 个样例技能目录实测 1 过 2 拒 |

---

## §1 T1 · 代码沙箱环境泄漏（P0-2）

### 1.1 病灶（基线代码）

`mcpserver/code_workspace/sandbox.py:251`（基线）把父进程环境整体摊给子进程：

```python
env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
```

`code_exec` 的输入是模型生成的 Python 片段。于是 `import os; print(os.environ)` 就能把
`OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、`GITHUB_TOKEN`、数据库口令整桌端出去。`:339` 的
`[sys.executable, "-c"]` 也不隔离：用户 site-packages 与 `PYTHON*` 系列变量照样生效。

### 1.2 闸门（本版）

三张**可被单测直接断言的表**（工单 T1-3 要求"不要散落在代码里"）：

| 表 | 作用 |
|---|---|
| `ENV_ALLOWLIST: frozenset` | 只列透传白名单：可执行查找（`PATH`/`PATHEXT`）、临时目录（POSIX/Windows/*BSD 三种写法）、系统根与用户目录定位、区域/编码、Windows 控制台的 `COMSPEC` 等 |
| `_SECRET_NAME_RE` | 名字命中即**永不**透传，即使被误加进白名单或从 `env_extra` 递进来也拦：`api[_.-]?key / access[_.-]?key / secret / token / passw / credential / authorization / bearer / cookie / private[_.-]?key / psk / secret[_-]?key`。工单点名的四类形状是下限，这里补了凭据同义词 |
| `ENV_FORCED_DEFAULTS` | 沙箱**主动设定** `PYTHONIOENCODING=utf-8`、`PYTHONDONTWRITEBYTECODE=1`。白名单只管"继承"，管不了"父进程根本没有"——不塞这两条会出真实回归（中文输出退回 GBK 变乱码；模型自拼 `python -m pytest` 往工作区撒 `__pycache__`，2026-10-22 实测） |

`build_child_env()` 三道闸顺序不可换：先按白名单挑，再用名字黑名单兜掉漏网凭据，最后叠加主动设定；返回 `(env, 被丢弃的变量名列表)`——**只报变量名，绝不报值**。

解释器参数同样成表：`PYTHON_ISOLATION_FLAGS = ("-I","-E","-B","-X","utf8")` 给 `code_exec`；`RUNTIME_ONLY_FLAGS = ("-E","-B","-X","utf8")` 给 `test_run`。

**为什么不统一带 `-I`**（诚实登记代价）：Python 3.11+ 的 `-I` 隐含 `-E -s -P`，并且实测会让 `sys.path` 不再自动含工作目录（`sys.flags.safe_path is True`）。`code_exec` 跑的是片段，可以要求先 `sys.path.insert(0, os.getcwd())`；`test_run` 要 import 刚写进工作区的模块，带 `-I` 会整片失败，所以它的隔离只靠环境白名单（`PYTHON*` 名字本就进不来）。

`cwd` 一律 `sandbox.session_workspace(session_id)`（`tools.py:92/219/270`），不继承调用方 cwd；沙箱外 cwd 起进程直接被拒（A/B 日志里那条 `拒绝在沙箱外执行进程: …\outside_caller_dir`）。

### 1.3 验收

- 命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_code_workspace.py -q` ⇒ **23 passed**（工单原文要求"原有 code_exec 用例全过（贴数量）"；报告 README 里"21 个用例"的数字要同步改掉）。
- 新增用例：`test_leaked_canary_not_inherited`（父进程设 `OPENAI_API_KEY=leak-canary`，子进程打印为 `None`，同用例断言 `PATH` 可见）、`test_child_runs_in_isolated_mode`（`sys.flags.isolated == 1`）、`test_env_allowlist_is_a_table_not_scattered_literals`、`test_forced_defaults_applied_even_when_parent_lacks_them`。
- A/B（`D:\my git\_wo269\logs\t1_ab.log`）：换入工单基线 blob 后，同一份探针在旧代码上把 canary 读得出来；本版 `leak-canary 命中 = False`。
- 变异对照（`t1_mutations.log`）：8/8 被抓，每次按 sha256 逐字节还原（`553d387269d34392`）。

---

## §2 T2 · 应用启动/开机自启的确认门（P0-7）

### 2.1 病灶（基线代码）

`NEKO/N.E.K.O/plugin/plugins/app_launcher/__init__.py`（基线 blob `5bc0c6118f`）里，三个 `@plugin_entry` 全部是模型可直接调用的入口，且都无确认门：

```python
# 基线 :886 set_autostart(app_id, enabled)  ← 单次调用
#   → _set_autostart_windows(...)
#   → 基线 :231 winreg.SetValueEx(key, reg_name, 0, REG_SZ, command)   # 开机即执行
```

- `add_app`（基线 `:507`）注册**任意路径**，`autostart=True` 顺手把这条路径写进 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`；
- `_is_valid_path()` 只判"像不像绝对路径"，不看存在性、不看类型、不认 `..` 与 UNC；
- `launch_app`（基线 `:651`）之后落到 `_launch_file()` 的 `os.startfile()` 分支——`type=="other"` 的条目执行什么**由外壳关联说了算**；
- `update_app` 改完路径还会"顺手刷新"自启项，等于把一条从没给人看过的命令写进 Run。

一次 `SetValueEx` 是跨重启的持久化写入：错过一次，下次开机就带着错的东西再跑一遍。

### 2.2 二选一，为什么两个都上

工单给的是「返回一次性确认令牌」**或**「直接退出模型可见面」，要求 PR 里说明理由。这里的取舍是**两层都做**，因为它们各自单独都不成立：

- **只做"退出模型可见面"**：`metadata.agent_auto=False` 只在路由阶段被读——`brain/task_executor.py:_is_plugin_entry_agent_hidden` 看 `agent_auto/agent_exposed/llm_exposed/agent_hidden`。它是**建议性**的：任何绕过路由器直接打 run 端点的调用（界面、脚本、别的编排层）照样能触发。更关键的是 `plugin.meta.json` 是主机读的**生成物**，插件刷新早已不再导入插件——代码改了、生成物没重算，等于没改。
- **只做"一次性确认令牌"**：入口仍在模型可见面上，模型可以调用、可以看返回体。只要 `confirmation_token` 出现在 `llm_result_fields` 里，模型第一次调用拿到令牌、第二次自己带回来，门就退化成了多绕一步。

组合起来的实际不变式：**令牌不进模型可见字段**（`llm_result_fields=["success","message","app_name","enabled"]`，`command`/`confirmation_token` 都不投影），所以模型侧即使命中入口也拿不到第二跳的凭据；而第二跳由 `static/index.html` 的 `confirm()` 发出——那是浏览器里的人点出来的，模型控制不了。路由标记只是少一次误触，函数级令牌才是真闸。

### 2.3 令牌语义

`_AutostartConfirmationGate`（进程内，`AppLauncherPlugin.__init__` 持有一份）：

| 属性 | 值 / 做法 | 理由 |
|---|---|---|
| TTL | 300s（`_AUTOSTART_CONFIRM_TTL_SECONDS`） | 够人读完弹窗并点一次，又不足以让人"待会儿想起来再点" |
| 一次性 | `consume()` **先 pop 再校验** | 失败的重试不能拿同一张票反复试 |
| 绑定 | sha256(`json.dumps({action, app_id, path, command}, sort_keys=True)`) | 令牌签发后换了路径/命令，指纹不等 ⇒ 自动作废，不给"确认一次、之后随便换命令"留口子 |
| 会话 | `scope = _ctx["conversation_id"]`（UI 直连时是空串） | A 会话签的票不能在 B 会话花 |
| 上限 | `max_pending=64`，超限按到期时间逐出最旧 | 反复"申请—不确认"不能无限堆内存 |
| 常量 | 三张表集中在模块顶部 | 派单表要求：可调、可断言，不散落 |

没有复用仓里现成的 `plugin/plugins/lifekit/_write_confirmation.py`：跨插件 import 会拉起 lifekit 整包 `__init__`（连带 msgpack 依赖），app_launcher 不该因为另一个插件装没装而失效。语义（TTL + pop-before-validate + payload 指纹 + scope）保持一致。

### 2.4 三个入口各自改成什么样

- `set_autostart(app_id, enabled, confirmed=False, confirmation_token="", _ctx=None)`
  开启方向：先按登记口径复核路径（`_reject_reason`），再过 `_authorize_autostart`；未授权 ⇒ **注册表一字节不动**，返回 `{success: False, needs_confirmation: True, command, confirmation_token, message}`，并 `logger.warning("Autostart confirmation required: id=… name=… command=…")`。关闭/删除方向**不设门**、立即生效——安全方向不该被摩擦挡住。
- `add_app(..., autostart=False)`：`_reject_reason(path)` 不过直接 `Err`（连清单都不进）；`autostart=True` 只登记软件 + 签发令牌，**不再**写 Run。老代码里"添加即自启"的合并写法取消。
- `update_app(...)`：新路径同样过 `_reject_reason`；路径变了且原来自启开着 ⇒ 先 `DeleteValue` 摘掉旧项、清掉标记（宁缺勿错），新命令若是 `.exe` 重新签发令牌，**旧的"顺手刷新"写法删除**。
- `_set_autostart_windows(..., log=...)`：唯一写点。写之前 `log("Autostart WRITE: hive=HKCU key={} value={} command={}", ...)`，只有被授权的那条路径会传 `log=self.logger.info`。测试按共享 trace 断言**顺序**：日志行必须在 `SetValueEx` 之前。
- `_launch_file(...)`：加了兜闸——`file_type not in _EXECUTABLE_TYPES` 直接拒，堵住老清单 `type=="other"` → `os.startfile()` 那条路。

`launch_app` **本来就是只认 `app_id`**（不接受调用方临时给的路径），工单第 3 条已经满足；这次用 `test_launch_app_only_accepts_registered_ids` 把现状钉住，防止后来人"顺手加个按路径直启"。

### 2.5 路径校验口径

`_reject_reason(path)`（返回空串即放行）按顺序拒绝：空路径 → UNC（`\\server\share`，开机时网络共享未必可达，且是外部可控载荷）→ 含 `..` 段 → 非绝对路径（`expandvars` 后仍非绝对）→ 扩展名不在 `_EXECUTABLE_TYPES = ("exe","lnk","url","script")` → 文件不存在。`_is_valid_path()` 已删除（被 `_reject_reason` 取代，避免两套口径）。

**这次唯一的真删，逐条交代**：推送前对账（`_wo269/t_diffcheck.py`）在 `__init__.py` 上报了 15 行"远端有而本地没有"，其中 **9 行是 difflib 的分块对齐假阳性**——`import subprocess`、`path = path.strip()`、去引号那三行、`os.path.expandvars(path)` 等，本地都还在（`_is_valid_path` 的函数体和取代它的 `_reject_reason` + `_resolve_path` 文本高度重合，匹配器把同一行对齐成了"一删一增"）。回查办法是把报删的每行拿去查本地行集合，`t_diffcheck.py` 现在内置这一步，并把真删做成必须逐个登记的白名单：没在白名单里的真删直接非零退出。剩下 **6 行是真删，全部属于 `_is_valid_path` 这一个函数**（def 行、docstring、两个空值判断、`if not os.path.isabs(path):`、`return True`）。删除是安全的，三条独立证据：①全文件 `grep _is_valid_path` 命中 0（基线在 `:67` 定义、`:553`/`:826` 调用，两个调用点都改成了 `_reject_reason`）；②新口径是旧口径的严格超集——旧的只查"非空 / 去引号 / expandvars / 绝对路径"，新的在这四条之外加了 UNC、`..`、扩展名白名单、存在性；③`expandvars` 与去引号在 `_resolve_path` 里原样保留，原先能登记的带引号路径现在照样能登记。`import subprocess` 也确实在用（`:137-157` 的 `Popen` 分支），不是被顺手删掉的导入。

**有意的收紧，要写进 PR**：登记时要求"文件必须存在"，先注册再安装的流程会被拒；老清单里 `type=="other"` 的条目从此不可启动，会明确提示"请重新登记为可执行文件"。

### 2.6 生成物必须同批交付

`plugin.meta.json` 是主机读的入口契约。这次用 NEKO 自己的 `write_packaged_metadata()` 原地重算（`plugin/neko_plugin_cli/core/metadata_probe.py:202`），可信度是先自证的：拿**未改动的基线树**跑 `derive_plugin_metadata()` 与仓内那份逐键比对，**10 个字段全等**，说明这条通道和上游生成器一致；改完再重算，差异只可能来自我的改动。

最终这份：`entries` 里只有 `add_app`、`set_autostart` 变了，`set_autostart` 现在带 `metadata {"agent_auto": false}` 与 `confirmed`/`confirmation_token` 两个入参，`llm_result_fields` 仍是 `["success","message","app_name","enabled"]`；`schema_version`(4)、`sdk_version`、`entry_methods`、`entries_config_sha256`、`build_env`、`source_files`(13 项) 全部不变；`source_bytes` 208794→234233、`source_sha256` `e971af51468aab86`→`af53fc24b8278308`。重算两次逐字节相同（幂等），probe 再跑一次 **相等字段 10 / 差异字段 0**。与远端 main 那份逐字段对账：`handlers`(26 项) 只有 4 项值不同，全是 `add_app`/`set_autostart` 两条描述各自出现两次（短名 + `plugin_entry:` 命名空间名）带来的连带变化，没有第三处。

8 个语言包同步补了 `entry.set_autostart.param.confirmed/confirmation_token` 与界面用的 `ui.confirm.autostart`、`ui.info.autostart_cancelled`（键集一致性由测试断言；162 键 → 166 键，八个文件键序完全一致）。

**这里踩过一个坑值得记**：补文案的脚本用 `json.load` → `json.dump` 整片重写，把原文件里那些只含两个空格的分组空行抹掉了——语义无损，但 8 个文件各多十来行纯格式 churn，属于"review 里看不见的内容变动"。推送前对账（`_wo269/t_diffcheck.py`）把它抓了出来，改成以远端那份为骨架做行级对齐、只替换我真正改过的行（`_wo269/t2_i18n_restore_fmt.py`，每步验 JSON 可解析 + 键集与恢复前逐一相等 + 新键在位 + LF 与结尾换行）。现在每个语言包与远端的差异是 **12 行**：3 行描述改写、4 行新增键、1 处末行补逗号，删除 0 行。语言包字节变了 ⇒ `plugin.meta.json` 必须再重算一次（上面的数字就是恢复格式之后的最终值）。


### 2.7 验收

- 命令：`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_app_launcher_autostart_gate.py -q` ⇒ **30 passed**（27 个函数，含 5 个参数化的恶意路径）。
- 工单验收原文「模型侧调用 `set_autostart` 不产生注册表写入（mock 断言 `SetValueEx` 未被调用 + 返回值含确认要求）」= `test_single_call_writes_no_registry`：假 `winreg` 记录器里 `registry_writes(events) == []`，返回体含 `needs_confirmation` 且 `command` 等于将来要写的那一条。
- 第二跳落盘的断言写法：`SetValueEx` 的**值必须逐字节等于刚才给人看过的 `first["command"]`**（"你看到什么就写什么"），不是等于某个解析后的路径。
- 变异对照（`D:\my git\_wo269\logs\t2_mutations.log`）：10 条改坏——摘路由标记 / 令牌投影给模型 / 不授权也写 / 不比指纹 / 令牌可复用 / 永不过期 / scope 不参与判定 / 登记不校验路径 / 落盘前不打日志 / 启动兜闸放行——**10/10 被抓**，每条都命中预期的用例，跑完按 sha256 逐字节还原并重跑回绿。
- **这次变异对照抓出一条假绿测试**：原来的 `test_scope_binds_the_token_to_the_calling_conversation` 用两个插件实例做 A/B 会话，而门是实例级的——换实例等于换门，令牌本来就不在里面，所以把 scope 判定整行删掉它照样绿。已重写为同一实例内 A 签发 / B 消费必须被拒 + 同会话签发消费必须放行（正对照），M7 现在能抓住。
- 全量回归：见 §4。

### 2.8 诚实边界

- 门在三个入口函数上。任何**新代码**直接调 `_set_autostart_windows` 可以绕过；当前除 `_authorize_autostart` 之后那条路径以外没有别的调用方，M3 钉住了这一点。
- 令牌是进程内存态：重启即失效（不会留下长期放行），也意味着签发与消费必须在同一插件实例里。app_launcher 是进程内插件，成立；真要多 worker，得把门挪到共享存储。
- 界面第二跳只有静态断言（`test_ui_asks_the_human_and_completes_the_second_hop` 检查 `needs_confirmation`/`first.command`/带令牌回跳）+ 手工验证，本仓没有 JS 测试框架。
- 测试用 `plugin.sdk.plugin` 的 sys.modules 门面桩（真装饰器、真 `EventMeta`，只是不拉 msgpack），`winreg` 换假模块、`_is_windows` 打桩——所以 Linux/CI 跑绿同样算数，且绝不碰真注册表。桩的存在是为了绕开"NEKO venv 里没有 pytest、本仓 venv 装不了 msgpack、而 NEKO 环境禁动"这三条同时成立的约束。
- 守卫测试放在**仓根 `tests/`**，不放进 `NEKO/`：`tools/sync_neko_upstream.py` 每次同步整片覆盖 `NEKO/**`，放进去等于随时可能被上游抹掉。

---

## §3 T3 · autoskill 转正前审查（P0-8）

### 3.1 病灶（基线代码）

`skills/autoskill/scripts/promote.py` 基线全文 47 行，做转正的只有三个动作：按
`new-skills` / `composition-recipes` 找源目录、看目标在不在、`shutil.move`。上游是
`fetch_window → redact → cluster → match_skills → synthesize`，即"屏幕采集 + LLM 生成"的产物，
**没有任何一只手读过内容**，一步就永久进 `skills/`——而技能目录里的东西是猫娘和人照着执行的。

### 3.2 闸门（本版）

1. **静态审查**（`review()`）。整棵树逐文件走：`.py` 用 `ast`（`Import`/`ImportFrom` 的顶层模块名
   命中 `_PY_DANGEROUS_MODULES`，`Call` 的函数名命中 `_PY_DANGEROUS_CALLS`），其余文本后缀
   用 `_TEXT_PATTERNS`（11 条命名编译正则）。三张表都在文件头部，单测直接断言表本身
   （`test_review_patterns_are_a_table_not_scattered_literals`），不为审查新增任何依赖。
   - `_PY_DANGEROUS_MODULES`：subprocess / socket / ssl / ctypes / winreg / smtplib / ftplib /
     telnetlib / paramiko / urllib(2/3) / http / requests / httpx / aiohttp；
   - `_PY_DANGEROUS_CALLS`：eval / exec / compile / `__import__` / urlopen / system / popen /
     startfile / registerserver；
   - `_TEXT_PATTERNS`：`rm -rf`、curl 下载并执行、curl/wget 出网、Invoke-WebRequest、远端 shell
     (ssh/scp/sftp/rsh/telnet/nc)、`-ExecutionPolicy Bypass`、`--force` 类、注册表写入
     (`reg add|import|delete` / `HKCU` / `HKLM` / `New-ItemProperty`)、SSH 私钥路径、`.env` 凭据文件、
     管道给解释器。
   - **扫不动的东西不算通过**：>1 MiB 的文本、带文本后缀但非 UTF-8 的文件，都记成
     "只进摘要未扫描（请人工确认）"的命中项；语法过不去的 `.py` 同样直接进命中。
     这里刻意不写 `except: pass`——审查器失明必须是命中，不能是静默。
2. **人工放行**（`--approve-reviewed <sha>`）。`review()` 同时算一份**内容摘要**：
   对每个文件 `sha256(字节)`，按 `"{相对路径}\t{文件sha256}"` 排序后再 `sha256`。
   摘要按内容寻址，所以"批过的就是这一份"是字面成立的：审完再加一个文件、或只改已有文件
   的一行正文，摘要立刻变，旧放行立刻失效（两条用例分开钉：
   `test_approval_does_not_survive_a_later_edit` / `test_in_place_edit_invalidates_approval`）。
   允许写 12 位以上前缀（`_approval_matches`），短于 12 位一律不算——12 位 ≈ 48 bit，
   不是让人猜的，是避免把整串 64 位抄错。
3. **默认 dry-run**。不带 `--apply` 一个文件都不动，只打印将要移动的路径、内容摘要与审查结论。
   这条默认值在**函数级**也成立（`promote(..., apply=False)` 返回 `None`），
   所以绕开 argparse 直接 import 一样搬不走东西。

**判定只住一处**：`_refused(findings, approved, digest)`。`main()` 和 `promote()` 都调它。
开发中途这里原本是两处各写一份（CLI 先判一次再打印，函数再判一次），M1 变异把它抓出来了
——"打印说 REJECTED、函数把文件搬走"这种分裂迟早会出现，所以合并成单一判定，并加了
`test_refusal_decision_has_exactly_one_home` 数引用点（把判断再抄一份进 `main()` ⇒ 立刻红，M11）。

**退出码**：`0` dry-run 或转正成功；`1` 用法/前置错（找不到提案、目标已存在）；`2` 审查未通过。
`2` 与 `1` 分开是给上层脚本看的：`1` 是"路径写错了"，`2` 是"要有人读内容"。

### 3.3 越界链接：符号链接之外还有联接点

技能包里带链就等于把目录外的一片东西一起转正。第一版只看 `path.is_symlink()`，本机实测发现
**Windows 目录联接点（junction）`is_symlink()` 返回 False**，而 `rglob` 照常递归进去——
并且造它**不需要任何特权**（`_winapi.CreateJunction` 普通用户就能成）。所以 `_is_escape_link()`
= `is_symlink() or is_junction()`（`Path.is_junction` 是 3.12+，用 `getattr` 兜底，老解释器退化为
只看符号链接而不是报错）。用例 `test_junction_inside_skill_is_refused` 里联接点指向的是
**完全正常**的代码（`def helper(): return 1`），内容扫描一条都命中不了，因此它测的是链接检测本身。
真正的符号链接用例 `test_symlinked_skill_file_is_refused` 在本机跳过（`WinError 1314 客户端没有所需的特权`），
链接类威胁由联接点那条实际跑起来覆盖。

### 3.4 工单点名保留的东西

两条既有报错原样保留，且有断言钉住（M10 改掉文案会红）：
`proposed skill {name!r} not found under {proposed_path}`、`target {target} already exists`。
"目标已存在"仍是先报再走（`review_proposal` 里检查），不做任何"自动合并/覆盖"。

**这个文件只有 2 行真删，都是搬家不是丢失**（对账明细见 §2.5 末段，同一条口径）：
`skills_dir = Path(skills_dir)` 被 `review_proposal` 里的 `target = Path(skills_dir) / name` 取代——
局部变量只为了下一行拼路径，改成就地转换，效果一致且少了"忘了转 Path 就 `/`"的空间；
`source = None` 连同它下面那个 `for kind in _KINDS` 循环一起抽成了 `find_source()`，
因为 `promote()` 和 `main()` 都要先定位提案，两处各写一遍循环正是上一节那条
"判定逻辑有两个家"的同类病。两种失败路径的行为不变：找不到仍返回 `None` 并抛同一条
`PromoteError`，这条由 `test_missing_proposal_error_is_preserved` 直接断言文案原文。

### 3.5 对调用方的影响

唯一调用方是 `skills/autoskill/scripts/autoskill.py:28-30`（`promote` 子命令转发 `args.rest` 给
`promote.main`），转发协议没变；但默认值从"直接搬"变成"先审再干"，所以
`skills/autoskill/SKILL.md` 的 §2「Review and promote」整节重写：三步命令序列、命中项含义、
`--approve-reviewed` 的用法、退出码表，以及"闸门在函数级、import 也一样拦"。流程图那行也从
`user-approved proposal → skills/<name>/` 改成 `review-gated promotion`。

### 3.6 验收（工单原文：造 3 个样例技能目录，跑 promote，期望 1 通过、2 被拒；贴三次输出）

素材：`_wo269/t3_build_samples.py` 造 `brief`（只读 json）、`cleanup`（`os.system`）、
`fetch`（`urllib.request.urlopen`）三份提案；脚本 `_wo269/t3_acceptance.sh`，全文输出落
`D:\my git\_wo269\logs\t3_acceptance.log`。三次 `--apply` 的关键输出（逐字粘贴）：

```
=== [2] 安全样例 brief —— 带 --apply（唯一该通过的）===
skill        : brief
content-sha256: d3c65cafafb3ad279f6c7693a9ca8b6b521a6642f90e2db6abca592a14df9eb1
review       : 无可疑模式
promoted: brief -> D:\my git\_wo269\t3_acceptance\skills\brief
rc=0

=== [3] 含 os.system 的样例 cleanup —— --apply 应被拒 ===
skill        : cleanup
content-sha256: aadf9cb55da7f7fdb0b46885b0bebd4fbba870248ce880be7176461d7e9b6b2c
review       : 命中 1 处可疑模式
  - scripts/cleanup.py:5: 调用 system()
verdict      : REJECTED —— 需要人工读过上面每一条，再带 --approve-reviewed <sha> 重跑
rc=2

=== [4] 含网络外发的样例 fetch —— --apply 应被拒 ===
skill        : fetch
content-sha256: 7a87380afbb963757fc713a915a770ff76ee98cf0d74fed8cbdcd26c3871fdbc
review       : 命中 2 处可疑模式
  - scripts/fetch.py:1: import urllib.request
  - scripts/fetch.py:5: 调用 urlopen()
verdict      : REJECTED —— 需要人工读过上面每一条，再带 --approve-reviewed <sha> 重跑
rc=2
```

被拒的两份留在原地、没进 `skills/`（同一份日志 [5]）：

```
skills/ :
  brief
new-skills/:
  cleanup
  fetch
```

人工放行的唯一出口（[6]，先 dry-run 取摘要，再带摘要重跑）：

```
拿到的摘要: aadf9cb55da7f7fdb0b46885b0bebd4fbba870248ce880be7176461d7e9b6b2c
review       : 命中 1 处可疑模式
  - scripts/cleanup.py:5: 调用 system()
verdict      : 人工放行（aadf9cb55da7f7fd…）后转正
promoted: cleanup -> D:\my git\_wo269\t3_acceptance\skills\cleanup
rc=0
```

默认 dry-run 那一跳（[1]，不带 `--apply`）：`verdict : DRY-RUN —— 没有移动任何文件`，`rc=0`，
`skills/` 空。

- 单测：`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_autoskill_promote_review.py -q`
  ⇒ **20 passed, 1 skipped**（跳过的那条是特权符号链接，见 §3.3）。
- 变异对照（`_wo269/logs/t3_mutations.log`）：11 条改坏——摘掉 `_refused` / 摘要比对恒真 /
  取消 12 位下限 / 摘要不看内容 / 去掉 dry-run 短路 / AST 空转 / 文本模式空转 / 链接检测关掉 /
  被拒退出码退化 / 改掉保留报错 / 把判定再抄一份进 `main()`——**11/11 被抓**，每条命中预期用例，
  跑完 sha256 逐字节还原并重跑回绿。
- 头两轮变异里抓出两条**我自己的测试/实现问题**，都已就地修掉，不是运气红：
  (a) 验收脚本一开始把子进程参数写成 `-X utf-8`（带连字符），实测 Python **静默忽略**它
  （`sys.flags.utf8_mode == 0`，stdout 仍是 gbk），中文审查结论被解成乱码，看起来像"闸门没输出"
  ——改成 `-X utf8` 并在测试里显式 `PYTHONIOENCODING=utf-8`；
  (b) 审查门在 `main()` 与 `promote()` 各有一份，M1 只让函数级那条红 ⇒ 合并成 `_refused()`。

### 3.7 诚实边界

- 这是**模式审查，不是沙箱**：正则+AST 只负责把可疑内容拦下来给人看，不做数据流分析。
  改名（`f = os.system`）、`getattr` 动态取名、字符串拼接的命令都能绕过名字匹配。所以口径是
  "命中即拒、放行要人读"，不是"通过即可信"；未命中不等于安全，`skills/` 里的技能照样按 §3.2
  的表继续被人工审。
- 只扫 `.py` 走 AST、其余文本后缀走正则；`.py` 里塞在字符串中的 `rm -rf` 不会被文本规则命中，
  但会被 `system()`/`subprocess` 命中——这是刻意选择（避免对 Python 正文乱开正则误报）。
  新增语言支持要同时补 `_TEXT_SUFFIXES` 和用例。
- 摘要覆盖全部文件（含二进制），扫描只覆盖文本类：所以"批过的这一份"包括未被扫描的内容，
  不会因为某个 `.png` 没扫就让它游离在放行范围外。
- `_approval_matches` 用前缀比较，是给人抄写用的；它不是密钥比较，也没有时序侧信道问题
  （拦的是"内容变了没"，不是"令牌对不对"）。真正的一次性令牌在 T2 那侧。


---

## §4 全量回归

三条命令跑的是同一份仓根 `tests/`，只差"我这批文件在不在场"（日志都在
`D:\my git\_wo269\logs\`，命令形如
`.venv/Scripts/python.exe -X utf8 -m pytest tests -q -p no:cacheprovider --no-header`）：

| 跑法 | 结果 | 日志 |
| --- | --- | --- |
| 基线：`--ignore=tests/test_app_launcher_autostart_gate.py`（T2 用例不在场） | **56 failed, 1744 passed, 19 skipped**, 283.40s | `full_tests_baseline_no269t2.log` |
| + T2 用例 | **56 failed, 1774 passed, 19 skipped**, 276.17s | `full_tests_t2.log` |
| + T2 + T3 用例（本批最终态） | **56 failed, 1794 passed, 20 skipped**, 270.93s | `full_tests_t3.log` |

- passed 差值可核对：1774−1744 = 30（T2 全部用例），1794−1774 = 20（T3 全部用例）；
  skipped 的 +1 是 T3 里那条需要特权的符号链接用例（§3.3）。
- **失败集合完全相同**：三份日志各自的 `^FAILED ` 行排序后做对称差
  （`comm -3 f_t3.txt f_base.txt`）——**空**。也就是说这 56 条一条不多一条不少，
  本批改动（含 T1 的沙箱环境白名单）没有引入任何新红，也没有顺手"修好"谁的旧红。
  核对命令：
  ```bash
  for f in full_tests_baseline_no269t2 full_tests_t2 full_tests_t3; do
    grep '^FAILED ' logs/$f.log | sort > /tmp/$f.txt
  done
  comm -3 /tmp/full_tests_t3.txt /tmp/full_tests_baseline_no269t2.txt   # 输出为空
  ```
- 三批用例合起来单独跑一遍，确认互不污染（T2 那批要用 `sys.modules` 门面桩 import NEKO 插件，
  早先用 `sys.path.append` 时曾把 `utils` 解析到 `agentserver/utils.py`、连带毒坏别的收集阶段，
  改成 `insert(0, ...)` 之后必须有一条"同场跑"的证据）：
  ```
  .venv/Scripts/python.exe -X utf8 -m pytest tests/test_code_workspace.py \
      tests/test_app_launcher_autostart_gate.py tests/test_autoskill_promote_review.py -q
  73 passed, 1 skipped, 2 warnings in 5.50s      # 23 + 30 + 20，与三条单独跑的总数一致
  ```
  单跑分别是 `23 passed in 4.44s` / `30 passed in 0.46s` / `20 passed, 1 skipped in 1.01s`。
- 这 56 条是本仓既有状态，不是本工单范围（工单硬边界只给了 P0-2/7/8），按测试文件分布：
  toolknit_mcp 14、duckdb_workbench 6、token_ledger / rf_workflow / law_tagging /
  agent_governance_hook / academic_interfaces 各 4、llm4decompile_adapter 3、
  law_case_import 3、writing_pipeline 2、pdf2md_adapter 2，其余 7 个文件各 1。
  可见原因里占比最高的是**可选依赖没装**：`duckdb` 8 次、`docx` 7 次、`casregnum` 3 次、
  `capstone` 2 次、`markitdown` 1 次（`ModuleNotFoundError`）；这些 import 都在被测模块里，
  属于运行环境缺件，不是代码断言失败。剩下的 toolknit_mcp / governance 一类要看各自的
  fixture 与外部服务，不在本批里头也不动它们——把它们顺手改绿会掩盖真实覆盖面。
- 单元测试之外的验证：`plugin.meta.json` 用 NEKO 自己的生成器重算并逐字段对回基线（§2.6）、
  `static/index.html` 的脚本块过 `node --check`、`promote.py` 过 `py_compile`、
  8 个语言包键集一致性由测试断言。


---

## §5 交付

**PR #401**：<https://github.com/fe1iscurc0r/scratchpad/pull/401>
分支 `wo/269-p0-exec-surface`，按任务三个提交，`main` 一个字节没动。

| 项 | 值 |
|---|---|
| base（= 分支父提交 = 远端 `main` 当时指针） | `c79b54e67acf45e47c621370f7c68e5a3a920587` |
| T1 提交 | `a781bf8a00e4` tree `95238776c2de`（3 文件） |
| T2 提交 | `8926b15a23f2` tree `93cb0c6d11ad`（13 文件） |
| T3 提交 | `acd8270baeca` tree `4e9b9203f8ba`（4 文件，含本文档） |
| 分支 tip | 交付的三个提交之上再压一个 docs 回填提交（本节就是它带上去的，故 tip 号写在这里只会自指，以远端 `git/ref/heads/wo/269-p0-exec-surface` 现值为准） |
| 远端核对 | `compare/main...wo/269-p0-exec-surface` ⇒ `status=ahead`、`merge_base=c79b54e67acf`、`total_commits=3`、20 文件、**removed 0**；PR 侧 `commits=3 changed_files=20 +2962 −396` |
| 回滚点 | 只删分支即可，`git push origin :wo/269-p0-exec-surface`（或 REST `DELETE /git/refs/heads/wo%2F269-p0-exec-surface`）；`main` 从未被写，所以 base 本身就是回滚点 |

推送通道是 GitHub REST + GCM 凭据（本机 git over HTTPS 被代理拦、`D:\my git\.git` 仍是坏的），
脚本 `D:\my git\_wo269\t_delivery.py`：默认 dry-run，`--apply` 才写，`--pr` 才开 PR；
base 钉死在 `EXPECT_TIP`，远端 `main` 一旦不是这个 sha 就停手；每个 blob 拿本地算出的
git blob sha1 与 API 返回值互核，不等即中止；上传前工作区 CRLF 归一成 LF。
凭据只在进程内流动，日志与本文档都不出现其值。

**推送前对账**：`_wo269/t_diffcheck.py`（结论落 `logs/t_diffcheck_final.log`）逐文件比对远端与本地，
把 difflib 的"删除段"回查成 **假阳性**（行只是挪了位置）与 **真删** 两类；真删必须逐个进白名单，
未登记即非零退出。本批真删 8 行，理由在 §2.5 末段与 §3.4 末段。这一道检查确实抓到了东西：
语言包重新 dump 时抹掉的分组空行就是它报出来的（§2.6）。

**交付途中我自己脚本的一个错**：第一次 `--apply` 在 T1 提交处 `KeyError: 'tree'` 崩了——
`repos/{repo}/commits/{sha}` 的 tree 嵌在 `commit.tree` 下，顶层没有 `tree` 键，
顶层 `tree` 只有 `git/commits/{sha}` 才有。崩点在 blob POST 之后、tree/commit/ref 之前，
所以远端只有三个游离 blob（无 ref 引用，会被 GC），`main` 与分支均未变动——
这一点是先查证再重跑的（`main` 仍 `c79b54e67acf`、分支仍 404），两个端点回同一个
tree `555fc8727ff2` 也顺带互为印证。

