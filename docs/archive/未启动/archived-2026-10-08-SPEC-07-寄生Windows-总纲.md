# SPEC-07 寄生 Windows 总纲 · v1

> **⏸ 状态：已搁置（2026-08-23 用户拍板）** —— 方向不成熟、难上仓库、野心过大，先缓缓。本文档仅存档，不派工、不排期、不推进。恢复条件：用户明确解冻。

> 用途：在天选7（Windows 11 24H2）建立「双通道寄生控制」，宿主 = 整个 Windows
> 读者：Trae / WorkBuddy / 沈遥（自包含）
> 日期：2026-08-23（补 2026-08-22 断网未落盘的三问：更新/桥接、UAC 判定、杀软信任）

## 〇、一句话定位

**不改造宿主，从外部建立控制。Windows 是天生可自动化的宿主（API 丰富 + UIA 树），寄生层 = 通道B（精确 API）+ 通道A（UIA/视觉通用层）+ 指挥层，三者共用一个审计与自检框架。寄生 ≠ 重装 ≠ 夺舍，只借力。**

## 一、双通道架构（2026-08-22 讨论定稿）

```
指挥层（Hermes / scratchpad / 天选7 本地优先）
  · 任务解析 · 双通道调度 · 状态同步 · 审计日志
        │
 通道B（精确）              通道A（通用）
  · PowerShell/Win32/COM    · UIA 控件树（半精确：拿句柄/属性）
  · WMI/WinRM               · screen_vision 填实（截图+本地视觉模型）
  · OpenSSH Server          · pyautogui/win32 注入
  · 现成资产复用            · 视觉兜底
  （lumo_fusion.ps1/NEKO/HamLog）
        │
  宿主 天选7 Windows 11 24H2（RTX 5060）
```

- **分工**：通道B 干脏活累活（文件/进程/注册表/服务），通道A 干"没 API 的活"（任意第三方 GUI）。
- **锚点**：状态同步 = UIA 树查到的状态 ↔ PowerShell 查到的进程/窗口状态交叉验证。
- **远程 vs 本地**：本地优先；远程只做受限通道（SSH + 指定端口，frp/Tailscale 不裸奔）。
- **原则**：一切动作幂等、可逆、有审计。watchdog 升级为「寄生层自检」：通道活吗？宿主状态对吗？有漂移吗？

## 二、三大天敌判定与对策（本次更新核心）

### 2.1 更新需不需要桥接？

**结论：更新不需要桥接，但桥必须对更新免疫。** Windows Update 走微软自家通道，寄生层不介入、不接管——这也是寄生哲学：不改造宿主。但更新是桥的头号杀手，三个破坏点：

| 破坏点 | 机制 | 对策 |
|--------|------|------|
| 重启断链 | 更新后系统重启，桥服务若不自启 → 永久失联 | 桥服务全部做成**开机自启**：OpenSSH Server 是 Windows 功能（自动启）、Tailscale 是系统服务、frp 用计划任务（`schtasks /create /SC ONSTART` / 登录触发） |
| 网络栈重置 | 更新期间网卡/防火墙规则重建，隧道掉线 | 桥客户端带自动重连（指数退避，参考 frp STCP wrapper 模式）；防火墙规则用 `New-NetFirewallRule -Profile Any` 固化 |
| UIA/驱动漂移 | 更新改控件树/显卡驱动 → 通道A 定位失效 | UIA 定位只用**属性匹配**（AutomationId/Name/ControlType），永不坐标硬编码；更新后跑锚点自检清单 |

**桥自身的更新（frp/agent 升级）走「双活切换」**：新版本先拉到备用路径 → 本地验证（`--version`/健康检查）→ 原子切换（改符号链接/计划任务指向）→ 旧版本留 7 天回滚窗口。**绝不在生产隧道上原地覆盖二进制**——更新半途断桥 = 自断后路。

**更新窗口协同**：
```powershell
# 活动时间避开自动重启（管理员）
# 设置：设置 → Windows 更新 → 高级选项 → 活动时间（默认 8:00-17:00 已够）
# 主动检查重启待定，更新前暂停自动化任务：
(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired' -ErrorAction SilentlyContinue) -ne $null
# → 为 True 时：挂起长任务 → 等重启 → 重启后跑「寄生层自检」三件套
```

**重启后自检三件套**（系统更新/手动重启后必跑）：
1. 通道B ping：`ssh 天选7 "echo ALIVE"` / PowerShell 远程可达
2. 通道A 锚点校准：UIA 树抽查 3 个关键控件（任务栏/目标应用主窗口）属性匹配仍命中
3. 服务清单核对：frp/Tailscale/SSH/寄生计划任务 全部 active

### 2.2 UAC 怎么判定？

**核心结论：自动化不点 UAC，也点不了——这是设计使然。**

**为什么点不了**：UAC 弹窗出现在**安全桌面**（Secure Desktop）。普通权限进程连它的窗口都枚举不到（`EnumDesktopWindows` 返回 0 + `ERROR_ACCESS_DENIED`），UIA 拿不到控件树，SendInput 也注入不进去。微软故意隔离，防的就是恶意软件静默点"是"。**任何宣称能程序化点 UAC 的脚本要么是已妥协系统，要么是假的。**

**判定方法（自动化怎么知道"这是 UAC"）**：

```powershell
# ① 进程级判定：consent.exe 存在 = UAC 弹窗正在显示
Get-Process consent -ErrorAction SilentlyContinue
# 非空 → 当前有 UAC 弹窗

# ② 安全桌面判定：当前线程桌面不是 Default = 在安全桌面
# PowerShell 无原生 API，用 C# inline：
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DesktopCheck {
  [DllImport("user32.dll")] static extern IntPtr GetThreadDesktop(uint id);
  [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
  [DllImport("user32.dll", CharSet=CharSet.Auto)] static extern int GetUserObjectInformation(IntPtr h, int i, IntPtr pv, int n, out int l);
  public static string Current() {
    IntPtr d = GetThreadDesktop(GetCurrentThreadId());
    IntPtr buf = Marshal.AllocHGlobal(256);
    int len; GetUserObjectInformation(d, 2, buf, 256, out len); // UOI_NAME=2
    string s = Marshal.PtrToStringAuto(buf); Marshal.FreeHGlobal(buf);
    return s; // "Default" = 正常桌面, "Winlogon" = 安全桌面
  }
}
'@
[DesktopCheck]::Current()  # Winlogon → 在安全桌面（UAC 弹窗期）
```

**对策（三层，按优先级）**：

1. **首选：根本不触发 UAC**。自动化跑在**标准用户权限**；需要管理员的操作**下沉到已提权的执行通道**：
   - 计划任务：`schtasks /create /TN "parasite-elevated" /TR "..." /RL HIGHEST /SC ONEVENT`（任务以 SYSTEM/最高权限跑，触发时无弹窗）
   - Windows 服务：以 SYSTEM 身份常驻，自动化通过命名管道/HTTP 触发
   - **自动化只负责"请求"，提权通道负责"执行"，UAC 弹窗从架构上消失。**
2. **会话内授权**：`gsudo`（第三方，免费）——第一次弹一次 UAC 换取会话内免提示；适合交互式运维，不适合无人值守。
3. **底线不可碰**：
   - ❌ `ConsentPromptBehaviorAdmin=0`（关 UAC）——自毁，杀软会跟进警报，且失去安全桌面保护
   - ❌ 用 `EnableLUA=0`——更糟，Windows 商店应用/沙箱全挂
   - ❌ 键盘模拟输密码过 UAC——安全桌面里根本收不到

**遇到弹窗的判定流程**：consent.exe 出现 → 判定"提权请求待确认" → 若是计划内操作：直接忽略（提权通道应该已经处理，出现弹窗说明通道没配好，记审计）；若是计划外：**挂起自动化 + 通知用户**，绝不尝试自动响应。

### 2.3 杀软怎么确定哪些是我的？哪些是病毒？

**Defender 的判定依据（按权重）**：
1. **签名库**：已知恶意特征。自己写的脚本没有特征 → 不因签名被杀（但也拿不到签名信任）
2. **信誉**：无签名的 exe / 带 Mark-of-the-Web（从网上下载的文件有 Zone.Identifier ADS）→ 低信誉。这是"下载的 frp.exe 被杀"的头号原因
3. **行为分析**（云保护 MAPS 开启时）：注入其他进程 / 写 Run 键 / 创建计划任务 / 监听端口 / 持久化 → 高危行为打分
4. **排除项**：用户显式声明的白名单

**"哪些是我的" = 排除项声明 + 行为克制 + 签名背书，三管齐下：**

```powershell
# ① 路径排除：寄生层代码统一放 C:\Parasite\（固定目录，未来一切资产都在这）
Add-MpPreference -ExclusionPath 'C:\Parasite'

# ② 进程排除：桥接/自动化守护进程（frp、agent 本体）
Add-MpPreference -ExclusionProcess 'frpc.exe','parasite-agent.exe'

# ③ 防火墙放行：本地监听端口不进弹窗、不被网络策略拦
New-NetFirewallRule -DisplayName 'Parasite Bridge' -Direction Inbound -Protocol TCP -LocalPort 2222 -Action Allow -Profile Any

# ④ 验证排除生效
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
```

**行为克制清单（让行为不触发行为分析）**：

| 行为 | 评价 | 替代 |
|------|------|------|
| 注入其他进程（WriteProcessMemory/CreateRemoteThread） | 🔴 高危特征 | 用 PowerShell 远程执行 / WinRM，不做进程注入 |
| 写 `HKCU\...\Run` 键持久化 | 🔴 经典恶意位置 | 用**服务**或**计划任务**持久化（更可信、可审计） |
| 键盘钩子/全局钩子 | 🟠 易被行为分析标记 | UIA 事件订阅替代 |
| 无签名 exe 从网上下载直跑 | 🟠 低信誉 | 下载后 `Unblock-File` 清 MOTW + 固定路径排除 |
| 监听 0.0.0.0 端口 | 🟡 正常但可疑 | 只监听 127.0.0.1 + 防火墙规则 + SSH 隧道转发 |
| 自签代码签名 | 🟢 加分 | `signtool sign` 自签 + 证书装进受信任根；企业环境可信，家庭版帮助有限 |

**判定边界（哲学层）**：杀软没有魔法。"哪些是我的"的显式声明 = 排除列表（路径/进程）；隐式声明 = 行为不像恶意（不注入、不钩子、不用 Run 键、代码签名、固定目录）。**排除列表要小、要固定、要可审计**——每加一条排除都在缩小 Defender 的保护面，所以只排除寄生层自身，不排除整个 C 盘。

## 三、施工路线（2026-08-22 定稿）

- **Phase 1**：打通通道B——天选7 装 OpenSSH Server + Tailscale/SSH 受限通道，云服远程指令闭环
- **Phase 2**：填实 screen_vision + UIA 做通道A——截图→本地视觉模型（RTX 5060 跑 large-v3-turbo）→控件树
- **Phase 3**：双通道状态同步 + watchdog 自检（含更新/UAC/杀软三件套检测）

## 四、验收标准（可执行不变量）

```powershell
# 1. 桥开机自启（模拟重启后）
Get-Service sshd | ? Status -eq Running        # 通道B 服务活着
schtasks /query /tn "parasite-bridge" | findstr Ready  # 桥计划任务就绪
# 2. UAC 架构验证：提权操作走计划任务，全程无 consent.exe 弹出
(Get-Process consent -ErrorAction SilentlyContinue) -eq $null
# 3. 杀软信任验证：寄生目录/进程在排除列表，Defender 实时保护仍开启
Get-MpPreference | Select ExclusionPath, ExclusionProcess
Get-MpComputerStatus | Select RealTimeProtectionEnabled   # 必须 True——排除≠关保护
# 4. 通道A 锚点：UIA 属性匹配命中目标应用主窗口
# 5. 状态同步：UIA 查到的窗口状态 == PowerShell 查到的进程状态
```

## 五、底线（不变）

寄生自己拥有的 Windows = 工具革命，全力建。寄生别人的 Windows = 入侵，拒绝。寄生 ≠ 破坏：借力不夺舍，控制即毁灭。

## 修订记录

- v1 (2026-08-23)：初版。补 2026-08-22 断网未落盘的三问：更新/桥接（2.1）、UAC 判定（2.2）、杀软信任（2.3）。架构与路线沿用 8-22 讨论定稿。
