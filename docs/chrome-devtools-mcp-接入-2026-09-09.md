# chrome-devtools-mcp 接入（W103-03 · 实测落地）

> 2026-09-09 · 上游：ChromeDevTools/chrome-devtools-mcp（51,395★，Apache-2.0，TypeScript，2026-09-09 活跃）
> 许可：Apache-2.0（授粉报告已复核）

## 一、架构拆解

- MCP server 工具集 29 个：DOM 操作（click/fill/fill_form/drag）、脚本注入（evaluate_script）、
  性能（performance_*）、截图（take_screenshot）、网络（list_network_requests）等。
- 浏览器控制：CDP（Chrome DevTools Protocol），连 `--remote-debugging-port` 的 Chrome/Edge。
- 安全模型：仅控制调试端口暴露的浏览器实例。

## 二、授粉三大件①：源→目标映射

| 源组件（chrome-devtools-mcp） | 目标模块 | 授粉方式 | 收益 |
|-------------------------------|---------|---------|------|
| DOM 检查/自动化（29 工具） | inspecting-hermes-desktop-dom（本地 CDP 技能） | 外部 MCP 互补 | 深度调试/性能分析 |
| CDP 封装 | 前端 E2E/桌宠 DOM 调试 | 外部桥接入 | 桌宠 DOM 检查 |
| 工具 schema（29 个） | mcpserver 工具生态 | 注册参考 | 工具面扩展 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处）

1. **页面对象模型**（page 句柄 + 选择器定位，McpPage.ts / McpContext.ts）：与本地 CDP 技能同构。
2. **工具注册循环**（src/index.ts:157-162 `createTools` → 逐工具 `#registerTool`）：
   外部 MCP 工具面组织参考——工具族按域分目录（src/tools/：console/emulation/input/lighthouse 等）。
3. **会话管理**（McpPage/McpContext 多页面句柄）：与 Pilot（87号）对照的浏览器会话模型。
> 行号引用基于 shallow clone 实读（D:/my git/haul-backfill/chrome-devtools-mcp）。

## 四、【落地】注册 + 实测（真实数据）

- 注册：`external_services.example.json` 登记 `chrome-devtools-mcp`（npx -y chrome-devtools-mcp@latest，
  默认 _disabled，启用即走 mcporter/external 桥）。
- 实测（真实跑码）：
  1. 本机 Chrome 151（用户级安装）以 `--headless=new --remote-debugging-port=9222` 启动成功。
  2. `tools/chrome_mcp_probe.py` 走 stdio JSON-RPC：initialize → tools/list → tools/call。
  3. **结果**：server `chrome_devtools` 初始化成功；**29 个工具**枚举成功；
     `list_pages` 返回真实页面列表 `1: about:blank [selected]`。
- 依赖：Chrome/Edge（本机已有）+ npx 首跑下载 npm 包（Node 22 WinGet 已装）。

## 五、与 inspecting-hermes-desktop-dom 边界划分

| 场景 | 用哪个 |
|------|--------|
| 桌面应用 DOM 快查（已有 CDP 技能） | inspecting-hermes-desktop-dom（本地，免装） |
| 深度调试（断点/性能/网络面板级） | chrome-devtools-mcp（29 工具全量） |
| 页面前端 E2E/表单自动化 | chrome-devtools-mcp（fill/fill_form/click） |

## 六、许可裁定与结论

Apache-2.0 可借鉴；结论：**接入（有条件）**——注册完成、实测有真实输出；默认禁用，
需要时置 _disabled=false 启用（需先起调试端口浏览器）。

---
*接入：fe1iscurc0r · 2026-09-09 · 实测数据：29 工具 + list_pages 真实输出*
