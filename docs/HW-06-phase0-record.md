# HW-06 Phase0 施工与验证记录（JLC-EDA 寄生链 · 第一环）

日期：2026-08-22 ｜ 执行机：天选7（Windows，按 SPEC v1 第十节"easyeda-agent 与 EasyEDA Pro 都装天选7"）

## 1. 已完成并验证

| 项 | 结果 |
|---|---|
| easyeda-agent v1.1.1 下载 | `D:\tools\easyeda-agent\easyeda_windows_amd64.exe`（16MB）+ `easyeda-agent-connector.eext`（1.7MB）+ checksums.txt |
| SHA-256 校验 | `45850ffd…f02337` 与 checksums.txt **一致** |
| daemon 启动 | `daemon start` 后监听 **60832**（0xEDA0），`/health` 返回 `{"status":"ok","version":"v1.1.1","windows":[]}` |
| typed 动作链路 | `project doc` / `project info` 返回结构化 JSON 响应壳（`id/type/version/ok/error`），无连接器时**优雅降级**返回 `NO_CONNECTOR` 类型化错误——协议层完整可用 |
| 离线读取脚本 | `scripts/easyeda/read_schematic.py`：live 模式走 daemon；file 模式解析 .epro(zip)/.esch/.json |
| 测试原理图 | `scripts/easyeda/testdata/mini_ldo_sch.json`（LM1117 LDO 最小电路：1 器件/3 引脚/3 导线/3 网络 VCC·GND·5V0），file 模式读取成功，inventory 与构造完全一致，退出码 0 |

## 2. 关键发现（影响 SPEC）

1. **SPEC v1 的 `eda.editor.getDocument()` 不存在**。用 `easyeda api search`（官方 @jlceda/pro-api-types 全量索引：93 命名空间/742 方法）查证：无 `editor.getDocument`；实际等价物是 `eda.dmt_SelectControl.getCurrentDocumentInfo(): Promise<IDMT_EditorDocumentItem>`（@beta）。SPEC v2 修订时应改引用。
2. **"云服安装 easyeda-agent"不可行**（原工单表述）：连接器插件必须跑在 EasyEDA Pro（桌面/Web GUI）进程内，Linux 无 GUI 云服只能跑 daemon（无意义）。SPEC 第十节已修正为天选7，本次按天选7执行。
3. 第三方 MCP 生态勘察：VLab-Software/easyeda_mcp（MIT，Node≥20，同样需要本机 EasyEDA Pro 活会话，且明确"不解析 .epro"）——本项目 Phase0 的离线 .epro 路线是差异化补充。参考副本在 github_haul/easyeda_mcp/。
4. easyeda-agent 自带 742 个官方 API 的离线自发现索引（`api search/list`）+ typed 动作目录（`actions`）+ 37 块验证过的电路块库（`blocks`，含 CH340/ESP32 自动下载）——Phase1/2 直接复用，不用重写封装。

## 3. 剩余阻塞（需要你人工做，约 15 分钟）

**2026-08-22 更新：以下已自动完成**
- EasyEDA Pro 已装在 `D:\lceda-pro\`（用户已打开运行中）
- easyeda CLI 已装到 `C:\Users\ASUS\bin\easyeda.exe`（~/bin 已在 PATH）
- easyeda-agent Skill 已装到 `~/.claude/skills/easyeda-agent/`
- Node 无需新装：Trae 自带 v24.18.0（`C:\Users\ASUS\.trae-cn\binaries\node\versions\24.18.0\node.exe`，未入 PATH，用到时全路径调用）

**剩余两步是 EasyEDA Pro 图形界面内的点击（无法无人值守，逆向侧载路径不可行——扩展装进 Electron profile 内部存储）：**

1. EasyEDA Pro → **扩展管理 → 导入扩展** → 选中 `D:\tools\easyeda-agent\easyeda-agent-connector.eext`
   （或扩展广场 jlc-ext.com 搜 "EDA Agent Connector" 一键装）
2. EasyEDA Pro → **设置 → 允许外部交互（Allow external interaction）** 打开
   ——不开这项，连接器 WebSocket 连不上 daemon

完成后跑（任意终端）：
```
easyeda daemon health
easyeda project doc
python scripts/easyeda/read_schematic.py live
```
预期：health 的 windows 非空且 connectorVersionOk=true；`project doc` 返回当前文档 JSON；脚本 ok=true。
（daemon 已在后台运行；重启机器后需重跑 `easyeda daemon start`）

## 4. 踩坑记录

- `easyeda daemon`（不带子命令）只打印帮助——正确启动命令是 `easyeda daemon start`（前台阻塞，需后台跑）。
- v1.1.1 起 daemon 端口固定 60832，若被旧实例占用会自动接管。
- Windows 下载资产名是 `easyeda_windows_amd64.exe`（不带 -agent），`.tar.gz` 后缀不存在，用 zip/裸 exe。
- 离线解析注意：EasyEDA std 格式的 id 形如 `nf_g1`，网络名提取要按位置取（netflag/netport 第 2 个元素），不能按字符串特征全扫。

## 5. 验收对照

- ✅ 脚本能读取一个测试原理图文档，返回结构化 JSON（file 模式 + mini_ldo_sch.json，实测通过）
- ✅ 验证记录注明测试文档、API 版本（easyeda-agent v1.1.1 / 官方 pro-api-types 93 命名空间 742 方法）、踩坑
- ✅ **live 模式实机闭环（2026-08-22 20:30）**：连接器导入 + "外部交互"开启后，2 个 EasyEDA 窗口注册成功（connector v1.1.1 ↔ CLI v1.1.1 匹配，easyeda 3.2.175，schematic.v1+pcb.v1 能力）；`project doc` 返回 `ok:true` + 结构化文档信息（首页标签 documentType=home/tabId=tab_page1）；`read_schematic.py live --window <id>` 实测通过；`project info` 无工程时返回结构化错误 `EDA_CALL_FAILED: No current project is open`（错误也是类型化的）。真实原理图页面的读取未单独留档（用户跳过），链路已证明等价——打开任意工程即可用同一命令读取。
- ✅ **用户最终确认（2026-08-22，实机 getDocument 闭环）**：中国版「嘉立创EDA专业版」（即 EasyEDA Pro 国内发行版）已安装（`D:\lceda-pro\`），`eda.sys_FileManager.getDocumentSource()` 经实机调用返回工程文档 JSON；插件链路（连接器/外部交互/文档 API）实测完成，HW-06 Phase0 验收项「getDocument 返回工程文档 JSON」**全部达成**。

## 7. 排障实录（连接器装了但连不上，20:12-20:30）

现象：连接器每 ~10s 重试注册，wsId 轮换 6 次全部"never accepted a registration"，daemon 日志零记录、netstat 无 ESTABLISHED。
定位：用 Python websockets 模拟连接器直连 `ws://127.0.0.1:60832/eda`——daemon 秒回 handshake（`{"service":"easyeda-agent","version":"v1.1.1"}`），证明 daemon 侧健康，问题在编辑器侧出口被拦。
根因：**"允许外部交互"是扩展管理器表格里每个扩展自己的列开关（扩展名称｜外部交互｜存储空间｜UUID），不是全局设置项**。没开时扩展的每次 `eda.sys_WebSocket` 调用直接抛异常（connector-contract.md 明文），连接器把它当连接失败无限重试。
解法：扩展管理器 → EDA Agent Connector 行 → 外部交互列 → "是"。开完 ~10s 内自动连上，无需重启编辑器。
另：连接器日志首行 `watchdog: worker unavailable — main-thread interval (throttled when backgrounded)` 是窗口后台化时定时器节流的正常现象，不是故障。
多窗口注意：两个 EasyEDA 实例并存时 CLI 动作会报 `AMBIGUOUS_WINDOW`，按提示带 `--window <id>` 或 `--project <name>`（read_schematic.py live 已支持同名参数）。

## 6. 附：WO-04 环境同步就绪（2026-08-22 补）

pycrdt 0.14.3 已装入 scratchpad/.venv；双副本离线编辑→交换 update→合并冒烟测试通过（不同字段全保留，同字段按 CRDT 序 LWW 收敛）。yjs/pycrdt 路线的环境风险已清零，WO-03 定案后可直接开工。

## 8. 工程生命周期指令流实测（2026-08-23，编辑器重启后闭环）

工具：`scripts/easyeda/project_lifecycle.py`（daemon + debug exec 逃生口调底层 eda.* API）。

| 环节 | 结果 |
|---|---|
| 创建 | ✅ `createProject('寄生链-自动验证-110925')` → uuid `06b62c19…320f`（exec_js 返回统一 `{value:...}` 包装，脚本已剥壳），随接 `openProject` 成功 |
| 打开 | ✅ daemon context 显示当前工程即新建工程（工程树含 Board1/PCB1/Schematic1/P1） |
| 归档 | ✅ `getProjectFileByProjectUuid(uuid,'epro2')` → File(10996B) → base64 → 桌面 `parasite-auto-test.epro`；zip 结构验证：project2.json + .epru 原理图 + IMAGE/。**全程零 GUI** |
| 迭代 | ⚠️ 部分阻塞：`copyProject` 静默返回 undefined；`importProjectByProjectFile` 需 newProjectOwnerTeamUuid（个人空间 uuid 未知，getCurrentProjectInfo / getAllProjectsUuid() 均不提供）。排查方向：编辑器网络层抓个人 team uuid，或等 easyeda-agent 把 DMT_Project 包成 typed action |
| 删除 | 未执行（测试工程保留供编辑器内查看；清理：`python scripts/easyeda/project_lifecycle.py delete 06b62c19bf094470aae9b35c93ab320f`） |

结论：**「必须打开 EDA 选工程」被推翻**——创建/打开/归档已全指令流；迭代只差 team uuid 的 API 暴露，非架构缺口。附带修复记录：扩展库两次失效（侧载与市场版同 uuid 冲突；编辑器切换存储源 client→pro.lceda.cn），经 IndexedDB 重置 + fork 换新 uuid 修复。
