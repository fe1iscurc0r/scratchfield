---
name: lumo-launch-control
description: 陆墨生态应用启动控制。一键启动/关闭/查询 NEKO 桌宠与 HamLog 电台日志。当用户要求"启动NEKO""打开桌宠""启动HamLog""打开电台日志""关掉NEKO""关闭HamLog"或询问这些应用是否在运行时使用。
version: 1.1.0
author: 陆墨
tags:
  - control
  - launcher
  - neko
  - hamlog
enabled: true
---

# 陆墨生态应用启动控制

通过 `agentType: "mcp"`、`service_name: "app_launcher"` 调用，管理陆墨生态桌面应用的启动、关闭与状态。

## 调用格式

```tool
{"agentType": "mcp", "service_name": "app_launcher", "tool_name": "启动NEKO"}
```

## 可用工具

| 工具 | 用途 | 参数 |
|------|------|------|
| `启动NEKO` | 启动 NEKO 桌宠（陆墨融合模式：注入人格+记忆+RAG） | 无 |
| `启动HamLog` | 启动 HamLog 电台日志 GUI（PyQt6 桌面程序） | 无 |
| `关闭NEKO` | 关闭 NEKO 桌宠窗口与后端（wrapper + Main Server） | 无 |
| `关闭HamLog` | 关闭 HamLog 电台日志 GUI | 无 |
| `查询生态应用状态` | 查询 NEKO / HamLog 是否在运行 | 无 |

## 使用说明

- **NEKO**：启动需 10-30 秒就绪（Main Server 端口 48911）。前置条件是陆墨后端带
  `LUMO_PROXY_TOKEN` 运行（即通过 `lumo_fusion.ps1` 启动的后端）；若后端是普通模式
  启动的，工具会明确报错并提示改用 fusion 方式重启后端，此时如实转告用户即可。
- **HamLog**：启动后用户首次使用需在 GUI 设置里填写本台呼号；之后 hamlog_adapter
  的 QSO/QSL 工具即可读到真实台账。
- 两个启动工具均幂等：应用已在运行时直接返回"已在运行"，不会重复拉起。
- 两个关闭工具同样幂等：应用未运行时返回"未在运行，无需关闭"。
- 关闭 NEKO 若返回"端口仍在监听"，说明是 fusion 脚本终端拉起的实例，需用户在那个终端 Ctrl+C。
- 用户问"NEKO/HamLog 起来了吗"时，先调 `查询生态应用状态` 再回答。

## 示例

用户："帮我把桌宠打开"

```tool
{"agentType": "mcp", "service_name": "app_launcher", "tool_name": "启动NEKO"}
```

用户："电台日志软件开一下"

```tool
{"agentType": "mcp", "service_name": "app_launcher", "tool_name": "启动HamLog"}
```

用户："把桌宠关了吧"

```tool
{"agentType": "mcp", "service_name": "app_launcher", "tool_name": "关闭NEKO"}
```
