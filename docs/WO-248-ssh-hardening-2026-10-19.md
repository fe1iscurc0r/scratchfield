# 工单 248 · SSH 加固收口（2026-10-19 防护文档落盘 + 验证矩阵 + 钥匙清单 + runbook）

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-248 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_248.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-248-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_248.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-19
> **触发**：师傅 08:14 在 QQ 下令"ssh 我建议你加强防护力度"。本单 + WO-246/247 同期。
> **施工范围**（已实际完成，沈遥亲自）：
> - `/etc/ssh/sshd_config.d/00-shenyao-hardening.conf` 落盘 14 项（按字母序在 cloud-init 前）
> - `sshd -t` 校验通过
> - `systemctl reload ssh` 后实测：`ssh -i id_hermes ubuntu@127.0.0.1` → `KEYAUTH_OK`；强制口令 → `Permission denied (publickey)`
> - `effective`：`permitrootlogin no / passwordauthentication no / maxauthtries 3 / login gracetime 20 / allowusers ubuntu,lighthouse`
> - `/etc/fail2ban/jail.local` 改：findtime 1h、maxretry 3、bantime 1w 递增、recidive 4w
> - 24h 内 fail2ban 已封 12 个 IP（103.188.*、109.160.*、154.201.*、35.244.* 等）；`总失败 1000` → 现有 sshd jail
> **剩余**：本工单做的是**收口**（文档 + 验证脚本 + 钥匙清单 + runbook），不是首次加固

## §0 · 现状（沈遥自检）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 14 项加固项落 `00-shenyao-hardening.conf` | ✅ | 优先级在 `50-cloud-init.conf` 前 |
| 2 | fail2ban recidive jail | ✅ | 但配置测过一次 `nftables_allports` 名字错，已改回 `nftables[type=allports]` |
| 3 | 钥匙清单（公钥指纹、来源、用途、撤销方法） | ❌ | 本工单任务 A |
| 4 | SSH 验证矩阵（10 个常见 case 的预期/实测） | ❌ | 本工单任务 B |
| 5 | SSH 维护 runbook（含"被锁在外面怎么办"） | ❌ | 本工单任务 C |
| 6 | 跟 11 月 GHSA 事件的关系（爆破 IP 段是不是同组织） | ❌ | 本工单任务 D（OSINT 研判） |
| 7 | 师傅笔记本公钥是否需要补 | ❌ | 师傅不走 SSH，orcaterm 直登 → **不需要**（但要写明） |

**核心痛点**：
- 师傅今天发现"24h 881 次爆破"才意识到要加固
- 加固配置本身没问题，但**怎么验证 / 怎么回滚 / 怎么处置被锁**没有 runbook
- 钥匙清单没维护，师傅也不知道自己有哪些 key 在用

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | ① 钥匙清单 1 份；② 验证矩阵 1 份（10 case）；③ SSH 维护 runbook 1 份（含回滚 + 被锁处置 + 钥匙轮换）；④ 爆破 IP 研判 1 段 |
| **M** Measurable | ① 钥匙清单覆盖 `~/.ssh/authorized_keys` 全部 2 行 + `~/.ssh/*.pub` 全部；② 验证矩阵 ≥ 10 case（公钥/口令/root/超限次/空口令/forwarding 等）；③ runbook 至少含"被锁怎么救"章节；④ 研判覆盖 12 个 banned IP 段 |
| **A** Achievable | 纯文档 + 1 段 OSINT 研判（用 web_search / 公开威胁情报 feed） |
| **R** Relevant | 师傅铁律"逆向/固件分析任务 → 委托 Hermes 做，他给目标我出方案" + 师傅对爆破频次敏感（10-19 实测） |
| **T** Time-bound | 1 天（W2 与 WO-246/247 同期 review） |

## §2 · 任务清单

### 任务 A · 钥匙清单

新文件 `scratchpad/docs/operate/ssh-keys-inventory.md`：

```markdown
# SSH 钥匙清单（2026-10-19 快照）

> ⚠️ 仅记录公钥指纹与用途。**私钥永不出仓**。

| 编号 | 私钥位置 | 公钥指纹 (sha256:...) | 来源/用途 | 备注 |
|------|---------|---------------------|----------|------|
| K1 | ~/.ssh/id_hermes | 3E2GeMFSok1pDlCJdtk4ds1un+BVRy8umQQ94FM73GM | hermes-bridge（沈遥自建） | authorized_keys #1 |
| K2 | ~/.ssh/id_ed25519 | +UwIURjLYkin/rGLxEQ79QQHi/5y3nX/6v22GHZ3puI | hermes-agent@kali-cloud（Kali 桥） | authorized_keys #2 |

## authorized_keys 全文（2 行）

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAD76UJnLStWMA7JuWsn4j6p  hermes-bridge
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMknnP0056KXcUfFLK8vRL1t  hermes-agent@kali-cloud
```

## 轮换流程

- K1 轮换：① 新 ed25519 keygen → ② 旧 pub 保留 7 天观察 → ③ 替换 → ④ 删旧
- K2 轮换：Kali 侧需配合，详 WO-XXX（待师傅起单）

## 撤销某把 key

```bash
# 把 authorized_keys 里该行注释或删
sed -i '/hermes-bridge/s/^/# /' ~/.ssh/authorized_keys
sudo systemctl reload ssh
# 验证
ssh -i ~/.ssh/id_hermes ubuntu@127.0.0.1
# 应得 Permission denied (publickey)
```

## 师傅本人 SSH 公钥

师傅不走 SSH（用 orcaterm 腾讯云控制台），不在 authorized_keys。
```

**Trae 必须做的**：把 `~/.ssh/authorized_keys` 真实 2 行拷过去，不要在仓里留新私钥。

### 任务 B · SSH 验证矩阵

新文件 `scratchpad/docs/operate/ssh-verification-matrix.md`：

| # | Case | 命令 | 预期 | 10-19 实测 |
|---|------|------|------|----------|
| 1 | 有效公钥登录 | `ssh -i id_hermes ubuntu@127.0.0.1` | 进入 shell | ✅ KEYAUTH_OK |
| 2 | 强制口令登录 | `ssh -o PreferredAuthentications=password ubuntu@127.0.0.1` | `Permission denied (publickey)` | ✅ 已验证 |
| 3 | root 登录 | `ssh -i id_hermes root@127.0.0.1` | `Permission denied` | （待 Trae 补） |
| 4 | 不在 AllowUsers 用户 | （lighthouse 已 allow；测试未知用户） | `Permission denied` | （待 Trae 补） |
| 5 | 错误公钥 | `ssh -i /tmp/fakekey ubuntu@127.0.0.1` | `Permission denied` | （待 Trae 补） |
| 6 | MaxAuthTries 超过 3 | （需 4 次错误） | 第 4 次 disconnect | （待 Trae 补） |
| 7 | 空口令尝试 | （publickey only, 不应进入） | 在公钥阶段就拒 | （待 Trae 补） |
| 8 | X11 转发 | `ssh -X` | 提示 `Warning: No xauth` | （待 Trae 补） |
| 9 | Agent forwarding | `ssh -A` | 允许（`AllowAgentForwarding no` 应禁） | （待 Trae 补） |
| 10 | 22 端口监听 | `ss -tlnp \| grep :22` | LISTEN 0.0.0.0:22 | ✅ |

**Trae 必做 case 1/2/3/5/10**（其余 4/6/7/8/9 标注"待师傅本人配合"也行，不要硬造结果）。

### 任务 C · SSH 维护 runbook

新文件 `scratchpad/docs/operate/ssh-maintenance.md`：

- **§0 现状**：14 项加固 + fail2ban（sshd + recidive 2 jail）
- **§1 钥匙轮换**（链接任务 A）
- **§2 fail2ban 操作**：
  - 查状态：`sudo fail2ban-client status sshd`
  - 解封某 IP：`sudo fail2ban-client set sshd unbanip 1.2.3.4`
  - 持久解封：编辑 `/etc/fail2ban/jail.local`，加 `ignoreip = 1.2.3.4`
- **§3 被锁在外面怎么办**（最关键的一节）：
  1. **永远别只留一种登录方式**——本机加固后**只能公钥**，但 orcaterm 腾讯云控制台仍可登录
  2. 应急回滚（在 orcaterm shell）：
     ```bash
     sudo sed -i 's/^PasswordAuthentication no/PasswordAuthentication yes/' \
       /etc/ssh/sshd_config.d/00-shenyao-hardening.conf
     sudo systemctl reload ssh
     ```
  3. 应急关 fail2ban：`sudo fail2ban-client stop`（不删 jail）
  4. 永远不要 `sudo systemctl stop ssh`（远程就连不回去）
- **§4 sshd 调试**：
  - `sudo sshd -T` 看有效配置
  - `sudo sshd -t` 校验语法
  - `sudo journalctl -u ssh --since "1h ago"` 看登录失败
  - `sudo journalctl -u ssh --since "1h ago" | grep "Accepted"` 看成功登录
- **§5 监控接入**：
  - 已通过 fail2ban（recidive 4 周）自动封 5+ 次的 IP
  - 师傅可在每日早报 cron 钩子里加 "Top5 爆破 IP"
- **§6 端口保留 22**：
  - 师傅没要求改端口；**保留 22** 因为 orcaterm / 移动端习惯
  - 改端口后师傅要 update 各处书签；ROI 不划算

### 任务 D · 爆破 IP 研判

新文件 `scratchpad/docs/incidents/2026-10-19-ssh-bruteforce-iplist.md`：

- 列出 fail2ban 现状 12 个 banned IP 段：
  ```
  154.201.89.198  43.129.193.109  109.160.32.114  35.244.60.50
  24.144.97.42    103.188.173.249 5.101.157.184  109.160.32.119
  109.160.32.180  103.28.38.181   109.160.32.145 177.136.239.234
  ```
- 段分析：
  - 109.160.32.0/19 多个相邻 IP（.114, .119, .145, .180）→ 同一 botnet 或云服务滥用
  - 103.188.173.x 和 103.28.38.x 属 APNIC 段（东南亚 IDC 常见）
  - 154.201.89.x 属 AS200651（FlokiNET，滥用历史）
- Trae 必做：
  - 用 `whois` 查每个 IP 的 netname / org
  - 看是否同 AS / 同 org
  - 跑 `abuseipdb.com` 查 reputation（不抓数据，引用即可）
- 写 1 段研判：是不是同一组织？是不是 botnet？要不要额外拉黑 AS？

## §3 · 验收标准

| 项 | 阈值 |
|---|---|
| 1. 钥匙清单 2 行真实（与 `~/.ssh/authorized_keys` 一致） | 必须 |
| 2. 验证矩阵 10 case 中至少 5 个实测（不要全标"待补"） | 必须 |
| 3. runbook §3 "被锁" 章节含 4 步应急 | 必须 |
| 4. 12 IP 研判至少给 1 段"是不是同组织"结论 | 必须 |
| 5. PR 描述含"24h 881 次爆破"和"12 IP 已封" | 必须 |

## §4 · 关联

- WO-246 / WO-247：同一窗口期
- fail2ban config 在 `/etc/fail2ban/jail.local`（系统级，备份 `jail.local.bak-shenyao-20261019-*`）
- sshd config 在 `/etc/ssh/sshd_config.d/00-shenyao-hardening.conf`（备份思路同）
- 师傅铁律"逆向/固件分析任务 → 委托 Hermes 做，他给目标我出方案"——本单没踩这条（属防御侧 OSINT 研判，沈遥自检）

## §5 · 验证证据（施工后由 Trae 填）

```
$ sudo fail2ban-client status sshd | grep -E "Banned|Total failed"
|- Total banned:    12
$ sudo sshd -T | grep -E "^(passwordauthentication|permitrootlogin|allowusers|maxauthtries)"
passwordauthentication no
permitrootlogin no
allowusers ubuntu
allowusers lighthouse
maxauthtries 3
$ cat ~/.ssh/authorized_keys | wc -l
2
```

## §6 · 编号防撞

- **指令文件**：`TRAE_WORKORDER_PROMPT_AGENT_248.md`（仓库根，input）
- **施工记录**：本文件 `docs/WO-248-*`（output）
