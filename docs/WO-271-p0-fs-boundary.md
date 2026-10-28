# 工单 271 · 文件系统边界收口（P0-12 / P0-13 / P0-20）

> ⚠️ **编号体系**：本文件是**施工记录**。指令原文是 `TRAE_WORKORDER_PROMPT_AGENT_271.md`（派单表 `P0-派单表-2026-10-22.md` 第二波）。
> 委托方：用户 · 执行：Qoder · 出单：沈遥 · 日期：2026-10-22
> **定罪基线**：`main@61835ad63625b6777ec880554536a87b8d46848c`
> **交付分支**：`wo/271-fs-boundary`（不动 `main`；PR 见文末）
> **本机等价关系**：本地 git 根是 `D:\my git`，`scratchpad-unified/` 一层对应远端仓根。下文所有远端路径按远端写法（不带 `scratchpad-unified/` 前缀）。

---

## §0 一句话结论

三个"路径由外部/历史决定、写入无人确认"的口子，各自加了一道**会在碰磁盘之前整批停下来**的闸，并且每道闸都被"改坏就必然红"的测试钉住：

| 项 | 病灶 | 收口方式 | 反证实验 |
|---|---|---|---|
| P0-12 | 上游 Git Data API 返回的 `filename` 是**远端可控字符串**，`LOCAL_ROOT / path` 对 `..`/绝对路径不设防 ⇒ 投毒的文件列表可以往仓库**外面**写、还能删掉外面不该删的东西 | `preflight()` 在任何磁盘动作之前过全批路径；命中即**整批中止**（退出码 2，一字节不动） | 注入实验：同一份恶意列表，基线代码越界写+误删成功，本版 `aborted:true` 且全盘 Δ=0 |
| P0-13 | 展示仓同步脚本只排除 46 条业务目录，`config.json`/`.env*`/`*.pem`/`id_rsa*`/`.auth_session` 等**根本没在排除表里**，末尾还直接建议 `git add -A` ⇒ 私有配置一把梭推进公开仓 | 敏感项进排除表（只增不减）＋同步后**自检**，命中就拒绝给提交命令并非零退出；`git add -A` 换成显式 NUL 白名单文件 | 四档场景：干净同步 0 命中 / 预埋脏文件 ⇒ rc=1 且不吐提交命令 / 46 条基线排除全保留 / 把自检改成恒假 ⇒ `.env` 真的被 staged |
| P0-20 | 三个遗留生成器把产物路径写死成**别人机器上的** `d:\my git\scratchpad\...`，且 `Out-File -Force` 静默覆盖被跟踪产物；`gen_mainjs.ps1` 更在**任何确认之前**先 `Remove-Item` 删产物 | `-OutPath` 变必填；去掉 `-Force`，改为"有差异必须 `-Overwrite`，且先落 `<name>.bak-<时间戳>`"；文件头钉一句"遗留生成器，改产物请改源重跑"；写盘改为**先落临时文件再比对** | 四脚本 × 五种调用矩阵全绿；跑完一整轮 `git status --porcelain` 指纹不变 ⇒ 工作区一字节没动 |

---

## §1 T1 · 上游同步路径越界（P0-12）

### 1.1 病灶（基线代码）

`tools/sync_neko_upstream.py:116`（基线）：

```python
for path, meta in sorted(changes.items()):
    target = LOCAL_ROOT / path          # ← path 是上游 API 给的字符串
    if meta["status"] == "removed":
        if target.exists():
            target.unlink()             # ← 删，且无边界检查
    ...
    target.write_bytes(data)            # ← 写，且无边界检查
```

`PurePath.__truediv__` 对绝对路径会**直接换根**（`LOCAL_ROOT / "/etc/passwd"` → `/etc/passwd`），对 `..` 会**往上跳**。也就是说：上游仓（或任何能往 `Project-N-E.K.O/N.E.K.O` 提 PR 的人）只要提交一个叫 `../../../outside/victim.txt` 的文件路径，这台机器的下一次同步就会照着写。

**为什么"写完校验 sha"挡不住**：`git hash-object` 是内容寻址，攻击者提交的 blob sha 与内容**天然自洽**。校验只能证明"我写的是 API 给我的那份字节"，不能证明"该写在哪"。所以必须在**落点**上做闸，不能在内容上做闸。

### 1.2 闸门（本版）

`_safe_target()` 三层，从便宜的到贵的：

1. **词法拒绝**：空串 / 绝对路径 / 盘符 `^[A-Za-z]:` / 反斜杠 / 空段（连续或首尾斜杠）/ `.` 与 `..` 段 / 段尾点或空格（Windows 会静默剥掉，落点≠请求名）/ 冒号（NTFS 备用数据流写到别的文件里）/ Windows 保留名（`CON` `PRN` `AUX` `CLOCK$` `NUL` `COM1-9` `LPT1-9`，不分大小写、忽略扩展名，`CON.txt` 一样撞设备命名空间）。
2. **`resolve()` + `is_relative_to(anchor)`**：词法过了再看真实落点还在不在子树里。这一层才是拦**符号链接/junction 引出树外**的（词法层看不出 `data/x.txt` 里 `data` 是个链）。
3. **`resolved != anchor.joinpath(*parts)`**：落点和请求名逐项对不上 ⇒ 说明中间某一跳被重定向，拒。

删除侧另加 `_safe_removal()`：位于 `.git/` 内 / 本身是符号链接（这是**本地状态**，上游无从描述，删它等于删本地私有东西）/ 是目录（上游只描述了文件）⇒ 拒。

`preflight()` 在 `sync()` 的**第一行**，在任何 `mkdir`/`write_bytes`/`unlink` 之前把整批过一遍，**列出全部违规**而不是第一个就返回：

```python
def sync(changes, *, write):
    violations = preflight(changes)
    if violations:
        return {"aborted": True, "violations": violations, "added":0, ..., "failed":0}
```

`main()` 收到 `aborted` 就打印清单并 `return 2`。退出码语义写进了模块 docstring：**0** 全一致或全写成功 / **1** 个别文件写失败 / **2** 安全闸整批中止。

工单要求的是"整批中止并列出违规路径（不是跳过）"——静默跳过会让人以为同步干净了，实际少了一批文件；中止 + 非零退出才会在人肉流程里响。

### 1.3 恶意路径用例表（`test_malicious_paths_rejected`，13 条参数化）

| # | 上游给的 filename | 命中哪层 | 拒绝理由（节选） |
|---|---|---|---|
| 1 | `../../etc/passwd` | 词法 | 含 `.`/`..` 段 |
| 2 | `/abs/path` | 词法 | 绝对路径 |
| 3 | `a/../../../x` | 词法 | 含 `.`/`..` 段（**混在合法段里也算**，不是只看开头） |
| 4 | `CON` | 词法 | Windows 保留名 |
| 5 | `NUL.log` | 词法 | Windows 保留名（忽略扩展名） |
| 6 | `C:\evil\x` | 词法 | 含盘符 |
| 7 | `dir\file.txt` | 词法 | 含反斜杠 |
| 8 | `a//b` | 词法 | 含空段 |
| 9 | `a/` | 词法 | 含空段（尾斜杠） |
| 10 | `a/../b` | 词法 | 含 `..` 段 |
| 11 | `evil.txt:` | 词法 | 含冒号（NTFS ADS） |
| 12 | `trailing.` | 词法 | 段尾点会被 Windows 静默剥掉 |
| 13 | `""` | 词法 | 空路径 |

符号链接/junction 两条走独立用例：`test_symlink_outside_repo_rejected`、`test_junction_redirect_inside_subtree_rejected`。

### 1.4 注入实验（决定性反证）

同一份恶意文件列表，喂给**基线模块**和**本版模块**，各自一棵沙盒树，跑完对比全盘 Δ。

> 两处一开始没打出来的坑，记在这：① 投毒 blob 必须用**合法 sha**，否则 sha 校验先短路，看不出越界；② `..` 的层数要真的跳出沙盒根，2 层不够（还在树内），实验会假绿。

```
--- A 基线 main@61835ad6（无闸） ---
  sync() 返回 : {"added": 0, "modified": 2, "removed": 1, "skipped": 0, "failed": 0}
  仓库外受害者 : 被覆盖 ⇒ b'written-by-a-poisoned-upstream-list\n'
  keep.txt     : 已删除
  pkg/mod.py   : 已写入
  全盘 Δ       : 3 项，其中子树外 1 项
       ~ 改内容  outside/victim.txt
       - 消失    repo/NEKO/N.E.K.O/keep.txt
       ~ 改内容  repo/NEKO/N.E.K.O/pkg/mod.py

--- B 本版（preflight + _safe_target） ---
  sync() 返回 : {"aborted": true, "violations": ["[写/删目标] '../../../outside/victim.txt': 含 '.' 或 '..' 段"],
                 "added": 0, "modified": 0, "removed": 0, "skipped": 0, "failed": 0}
  仓库外受害者 : 原样 ⇒ b'the only copy of something that matters\n'
  keep.txt     : 仍在
  pkg/mod.py   : 未改
  全盘 Δ       : 0 项，其中子树外 0 项
```

注意 A 的 `failed: 0` —— 基线代码觉得自己干得很漂亮：改了 2 个、删了 1 个，零失败。危害恰恰统计在"成功"里。

### 1.5 改坏⇒FAIL 变异表（9 条，`logs/mutate_t1.log`）

| 变异 | 破掉的防线 | 结果 |
|---|---|---|
| M2 | `preflight` 吞掉违规（=工单明令禁止的静默跳过） | 4 failed |
| M3 | 整条闸门撤掉，逐字回到 `main@61835ad6` 的拼法 | 4 failed |
| M4 | 删 `resolve()` 后的子树复核 | 2 failed |
| M5 | 删"落点与请求名不符"判定 | 1 failed |
| M6 | 删 Windows 保留名判定 | 5 failed |
| M7 | 删删除侧 `.git/` 判定 | 2 failed |
| M8 | 删删除侧"目录不给删"判定 | 1 failed |
| M9 | 词法层删"段尾点/空格"判定 | 1 failed |
| M10 | `main()` 中止分支不再返回非零 | 1 failed |

9/9 全部由绿转红；跑完 sha256[:12] 还原校验一致（`216c60da8d15`），复跑 32 passed。

M3 换过一次写法：原先删 docstring 那个变异只会触发 `SyntaxError`，属于"编译期就红"，证明不了行为，改成"撤 `preflight` 调用 + 回到 `LOCAL_ROOT / path`"之后才是真正的行为绕过。

### 1.6 前后对照

基线模块（REST 取回的 `main@61835ad6` 原样 blob）换进工作区跑**同一份**测试：`1 error during collection — module has no attribute 'UnsafePath'`（基线里根本没有闸门这个东西）；换回新版 `32 passed`，新版文件 sha256 前后一致。

---

## §2 T2 · 展示仓同步脚本（P0-13）

`scripts/sync-to-scratchfield.sh` 把私仓选料 rsync 进公开展示仓，然后打印一行 `git add -A && git commit && git push`。原来那 46 条 `--exclude` 全是**业务目录**（`papers/` `data/` `workorders/` `github_haul/` …），一个敏感文件模式都没有。

### 2.1 改动

- 排除项**只增不减**（工单硬边界）。新增 8 条从一个数组派生，排除表和自检共用同一份真相：

```bash
SENSITIVE_GLOBS=( 'config.json' '.env*' '*.bak*' 'token_usage.json' '.workbuddy' '*.pem' 'id_rsa*' '.auth_session' )
```

- 同步后自检：用同一个数组现搭一条 `find` 表达式扫 DST，命中就**拒绝给提交命令**并非零退出。
- `git add -A` 换成显式白名单：已跟踪的取 `diff --name-only -z --no-renames HEAD`，未跟踪的取 `ls-files --others --exclude-standard -z`，`sort -z -u` 后落成 NUL 分隔清单文件，命令是 `git add --pathspec-from-file=<list> --pathspec-file-nul`。

### 2.2 本机踩到的四个坑（都写进注释了）

1. **这台机器没有 rsync** —— 验收用 stub 替身跑（见 §4 ⛔ 清单），排除表**参数级**对账，不谎称验过同步引擎本身。
2. `set -e` 撞上 `[ cond ] && cmd`：条件为假时整行退出。
3. `mapfile -d '' -a ARR` 写法无效（产品里是真 bug，被验收脚本抓出来的），正确是 `mapfile -d '' ARR`。
4. 模式剥前缀的顺序必须先 `${pat%/}` 再 `${pat#**/}`，反过来会把 `data/` 剥成空模式。

### 2.3 四档场景输出

**A 干净同步**（敏感项留在 SRC 不带进 DST）——9 类敏感样本一个没进，自检 0 命中：

```
== 敏感文件自检: 0 命中
== 待提交 4 项（前 20）:
     app/main.py
     docs/readme.md
     plugins/tool.py
     scripts/sync-to-scratchfield.sh
== 提交（显式白名单，**不要用 git add -A**；清单文件重启会回收，尽快用）:
   git -C "…/dstA" add --pathspec-from-file="/tmp/tmp.HdGSdXZGdc" --pathspec-file-nul
```

**B 预埋脏文件**（DST 里事先有 `.env` + `config.json`）：

```
!! 敏感文件自检命中 2 项 —— 这些东西不能进公开仓 …/dstB：
     .env
     config.json
!! 未给出提交命令。私密就移出/删除；确实要公开的，改 SENSITIVE_GLOBS 并在 PR 里写理由。
```
rc=1，且**没有打印任何提交命令**。

**C 排除表对账**：基线 46 条一条不少，8 条敏感 glob 确实到达 rsync argv。

**D 把自检的命中判定改成恒假**（其余一字未动）——这是"改坏⇒行为失守"的反证：

```
== 敏感文件自检: 0 命中
== 待提交 3 项（前 20）:
     .env
     config.json
     scripts/sync-to-scratchfield.sh
```
rc=0，照打印的命令执行 ⇒ `.env` 真的被 staged。P0-13 的泄密链路在防线失守时确实能打通，所以 B 档 rc=1 挡的是真东西。

> 注：A 档待提交里出现 `scripts/sync-to-scratchfield.sh` 是**正常**的——沙盒 SRC 里就有这个文件，被当成选料同步过去了，不是脚本自己改自己。

---

## §3 T3 · 遗留生成器写死路径（P0-20）

### 3.1 基线行为（REST 取回的原 blob）

| 脚本 | 基线干了什么 |
|---|---|
| `write_main.ps1` | `$path` 写死 `d:\my git\scratchpad\wt-overwatch-v6\js\main.js`；`Out-File -Force` 静默盖被跟踪产物 |
| `write_main.js.ps1` | 同上形状 |
| `gen_mainjs.ps1` | **最狠**：第 4 行 `Remove-Item $path -Force -ErrorAction SilentlyContinue` —— 在任何确认之前先把产物删了，生成失败就没了 |
| `wt-overwatch-v6/js/gen_mainjs.ps1` | 根目录那份的逐字节相同副本；REST 查证远端**同样跟踪**（基线 blob `3534e0a1` 与根目录那份相同）⇒ 一并交付 |

> 本机 git 根是 `D:\my git`，`scratchpad-unified/` 一层映射远端仓根，所以本地 `git ls-files` 看它"未跟踪"是本地索引的事，与远端跟踪状态无关。交付以远端为准。

### 3.2 本版统一形状

```powershell
# 遗留生成器（工单271 T3 / P0-20）：产物 wt-overwatch-v6/js/main.js 已入库。
# 要改行为请改这个源并重跑，别直接编辑产物 —— 重跑会把它盖掉。
# 输出路径不再写死在别人机器上：必须显式给 -OutPath。
param(
    [Parameter(Mandatory)][string]$OutPath,
    [switch]$Overwrite
)
```

写盘改成**先落临时文件再比对**：内容一致 ⇒ 直接 `exit 0` 不碰盘；有差异且没给 `-Overwrite` ⇒ `Write-Error` + `exit 1`，**不产生备份**；给了 `-Overwrite` ⇒ 先 `Copy-Item` 成 `<name>.bak-<yyyyMMdd-HHmmss>` 再覆盖。`gen_mainjs.ps1` 顶部那两行 `$path=…` / `Remove-Item $path -Force` 已删除。

### 3.3 验收输出（四脚本各跑一遍）

`-?` 两种形式的**贴输出**：

```
--- write_main.ps1 -?（-Command 形式，打印 PS 的参数语法行）
    write_main.ps1 [-OutPath] <string> [-Overwrite] [<CommonParameters>]
    rc=0
    ✓ 语法行显示 -OutPath 是必填项，脚本体根本没跑
--- write_main.ps1 -?（-File 形式 + 同时故意给 -OutPath）
    rc=0 输出 0 字节
    ✓ 指定的 -OutPath 没有被创建 ⇒ 这一路 -? 不落盘
--- write_main.ps1（不给 -OutPath）
    D:\my git\scratchpad-unified\write_main.ps1 : 无法处理命令，因为一个或多个强制参数丢失:  OutPath。
        + CategoryInfo : InvalidArgument: (:) [write_main.ps1]，ParentContainsErrorRecordException
        + FullyQualifiedErrorId : MissingMandatoryParameter,write_main.ps1
    ✓ rc=1（参数缺失就退出，没有落盘）
    ✓ 报错只谈参数，不再指向旧硬编码路径
```

这里有个 PowerShell 事实值得记：`powershell.exe -File x.ps1 -?` 的 `-?` 被 **powershell.exe 自己的开关解析**吃掉了（rc=0、0 字节输出、脚本体一行未执行），所以光看这一路拿不到语法行。要拿到 `param()` 块渲染的语法必须走 `-Command "& '<path>' -?"`。两种都跑并都断言了"没落盘"。

行为矩阵（四脚本全绿，节选一份）：

```
--- 脚本 write_main.ps1
  ✓ 新建：rc=0，写出 13 行
  ✓ 同版本重跑：rc=0 且明确报「一致，未改动」（sha 前后=9f5c5c948868）
  ✓ 有差异且无 -Overwrite：拒绝（rc=1），未覆盖（sha=df3fb2cb5734）、未造备份
  ✓ -Overwrite：备份=write_main.js.bak-20261022-141810（内容=被改过的那份 sha=df3fb2cb5734），产物已重写回 sha=9f5c5c948868
```

全轮跑完后：

```
════════ e) 整轮跑完后工作区是否被动过 ════════
  ✓ git status --porcelain 指纹前后一致（b15136a7bd13）⇒ 四个脚本跑遍所有调用方式，工作区一字节没动
```

旧代码写死的 `d:\my git\scratchpad\wt-overwatch-v6\js\main.js` 前后 `absent`（这机器上那个路径压根不存在，正好是最干净的证明）。

### 3.4 本轮挖出并修掉的一个**真产品 bug**

改完加中文注释后，三个脚本一跑就报 5 个 PowerShell 解析错（"字符串缺少终止符"之类），退出码 1。根因不在脚本逻辑：

> **Windows PowerShell 5.1 按 ANSI/GBK 解码没有 BOM 的 `.ps1`**。UTF-8 无 BOM 的中文注释被按 GBK 读，多字节序列会**吃掉相邻的引号**，把下一行字符串撕开。

先确认基线那三份文件解析干净（它们没有中文），再统计全仓 `.ps1`：15 个（不含 `node_modules`/`NEKO`），其中 8 个含非 ASCII，而这 8 个里 **3 个已经带 BOM**（`lumo.ps1` `lumo_fusion.ps1` `setup.ps1`）—— 前人已踩过同一个坑并留了正确解法。据此给改动的 4 个 `.ps1` 统一加 UTF-8 BOM ⇒ 解析错 0。

> 这不是"加了个装饰"。**不带 BOM，中文注释版脚本直接不跑**。`.gitattributes` 里 `.ps1` 没声明 `eol`，走 `* text=auto eol=crlf`，工作区是 CRLF；BOM 与 CRLF 一起构成本机可用的 ps1。

同理，验收脚本一开始也"误报"了三条 `✗ 同版本重跑异常 rc=0`：PS 5.1 控制台输出是 cp936，bash 里直接 grep UTF-8 中文必然不中。**是量具错不是产品错**——日志改过 `iconv -f cp936 -t utf-8` 再断言，三条同时转绿，`rc=0` 与 sha 未变这两条硬证据从头到尾都是对的。

---

## §4 ⛔ 诚实清单（本机做不到的，不粉饰）

1. **没有 rsync** —— T2 的同步引擎本身没被真跑过。用 stub 替身只验到"排除表参数正确到达、脚本控制流正确"，**没验**真实 rsync 对这些 glob 的匹配语义。换到装了 rsync 的机器上应重跑场景 A。
2. **造不出真符号链接** —— 无开发者模式，`os.symlink` 返回 errno 22。改用了两个替代：目录 **junction**（`New-Item -ItemType Junction`，无需提权，`Path.resolve()` 会跟、但 Python 3.12 的 `is_symlink()` 对它返回 False —— 这点已写进注释），以及 monkeypatch `Path.is_symlink` 专门覆盖"删除侧遇符号链接"这条分支。**junction 与 symlink 的判定不完全等价**，`_safe_removal` 的符号链接分支在本机是靠打桩过的。
3. **没有 CI** —— 所有绿都是本机 `.venv`（Python 3.12.13）跑的。远端没有流水线会替你复跑。
4. **没跑过真实上游同步** —— 工单硬边界 `--write` 一律不跑。`_safe_target` 面对的**真实**上游路径集（含 Unicode、含 weird name）没有过闸记录，只有参数化用例。
5. **`.bak-<时间戳>` 会堆文件** —— 每次 `-Overwrite` 落一个备份，没有回收策略。故意留的（宁可堆文件不要静默覆盖），但要人肉清。
6. **`git add --pathspec-from-file` 需要 git ≥ 2.25** —— 本机 2.56.0 可以，别的机器上不保证；清单文件在 `/tmp`，重启回收，命令里已注明"尽快用"。

---

## §5 一处与工单验收标准不一致的发现（不藏着）

工单 T3 验收写的是仓库级：`grep -rn "d:\\my git" --include='*.ps1' .` **0 命中**。

点名的三个脚本（加副本共 4 个）已经做到 0：

```
write_main.ps1:0  write_main.js.ps1:0  gen_mainjs.ps1:0  wt-overwatch-v6/js/gen_mainjs.ps1:0
```

但仓库里还剩 **3 处**，都在**正在用的启动器**里，不在 T3 范围：

```
./lumo.ps1:24:        $NEO4J_BAT    = "d:\my git\neo4j-community-5.26.2\bin\neo4j.bat"
./lumo_fusion.ps1:80:   "d:\my git\neo4j-community-5.26.2\bin\neo4j.bat"  # 历史默认
./_serve.ps1:2:       $root = 'd:\my git\scratchpad\lumo-task-tracker'
```

**为什么没顺手一起改**：P0-20 的病因是"生成器写死路径 + `-Force` 静默覆盖产物"，危害是**盖/删别人的产物**。这三处是**读**本机工具路径的活体启动器（`lumo.ps1` 是你现在起全家桶用的；`lumo_fusion.ps1:80` 已经在一个候选列表里、注释写明"历史默认"，属于正确的做法）。把它们改掉是**行为变更**，可能直接让服务起不来，收益只是让一条 grep 归零。按"范围跟着危害走、不跟着 grep 走"的原则，本单不动，留给单独一张单：如果要把这类路径收口，正确做法是统一成 `lumo_fusion.ps1` 那种 `Resolve-ToolPath` 候选+环境变量形状，不是简单替换字符串。

`_serve.ps1:2` 是唯一一处指向**已不存在目录**（`scratchpad/lumo-task-tracker`）的死路径，跑起来必挂，但它同样不在 T3 的"生成器"范围内，且看着像临时调试遗留 —— 要不要删，等你一句话。

---

## §6 交付物

| 路径（远端写法） | 状态 | sha256[:16] |
|---|---|---|
| `tools/sync_neko_upstream.py` | 修改 | `216c60da8d157a1e` |
| `tests/test_sync_neko_upstream_paths.py` | 新增（32 用例） | — |
| `scripts/sync-to-scratchfield.sh` | 修改 | — |
| `write_main.ps1` | 修改（UTF-8 BOM） | — |
| `write_main.js.ps1` | 修改（UTF-8 BOM） | — |
| `gen_mainjs.ps1` | 修改（UTF-8 BOM） | — |
| `wt-overwatch-v6/js/gen_mainjs.ps1` | 修改（远端同样跟踪的副本，一并交付） | — |
| `docs/WO-271-p0-fs-boundary.md` | 本文件 | — |

开工前用 REST 逐文件核对过"基线 blob == main tip blob"（6 条路径，见 `logs/`），全部 `基线==tip ✓` ⇒ 整文件替换不会回退别人的新改动。

---

## §X 修复记录（2026-10-23，合并前收口）

### 现象

`tests/test_sync_neko_upstream_paths.py` 有 3 条**确定性失败**（不是偶发）：

```
test_symlink_outside_repo_rejected          → DID NOT RAISE UnsafePath
test_junction_redirect_inside_subtree_rejected → DID NOT RAISE UnsafePath
test_preflight_lists_every_violation_not_just_first → 期望 3 条违规、实际 2 条
```

### 根因：**`os.symlink` 假成功 + 早返回**，导致永远走不到能用的 junction 分支

`_mkjunction()` 原实现：

```python
try:
    os.symlink(target, link, target_is_directory=True)
    return              # ← 这里
except OSError:
    pass
out = subprocess.run([... New-Item -ItemType Junction ...])
```

实测：本机 `os.symlink` **不抛异常**，但产出的链接是坏的——
`os.path.islink=False`、目标不可达、`link.resolve()` **不跳转**。

于是：`return` 早退 ⇒ **junction 分支从未被执行** ⇒ 链接实际不存在 ⇒
后面"应当被拒"的断言全部空转。

**判定实验**（不经 pytest，纯 Python）：

```
链接建成: symlink | os.path.islink: False | 目标文件可达: False
link.resolve(): ...\local\outlink        ← 没跳到 target
_safe_target('outlink/victim.txt')        → 未被拦
```

### 修法（两件事）

1. **`_mkjunction` 重写**：两条路都试（symlink → junction），每次都用
   `link.resolve() != link and link.is_dir()` **校验是否真的重定向**；都不行才 `pytest.skip`
   （平台门控；注意旧版是"两条都失败就 `pytest.fail`"，现在是"造不出就 skip"）。
2. **补两条不依赖真链接的用例**（`test_escape_detected_via_stubbed_resolve` /
   `test_redirect_inside_subtree_detected_via_stubbed_resolve`）：
   monkeypatch `Path.resolve` 直接模拟"解析结果跳到树外 / 跳到树内别处"，
   把**判定逻辑**本身钉住，任何平台都能跑。

### 验收

```
pytest tests/test_sync_neko_upstream_paths.py -q
→ 34 passed（原 29 passed / 3 failed；--randomly-seed=3 / 11 均 34 passed）
```

> 关键点：这 3 条现在**不是靠 skip 变绿的**——重写后 junction 分支真正执行、链接真的会重定向，
> 闸门的 `resolve()` 复核确实把它们拦下来了。
