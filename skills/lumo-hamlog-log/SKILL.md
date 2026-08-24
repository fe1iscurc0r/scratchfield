---
name: lumo-hamlog-log
description: 陆墨的 HamLog 电台日志管理。帮用户录入 QSO 通联记录、搜索日志、查 QSL 卡债、更新 QSL 收发状态、生成 QSL 卡填写内容。当用户说"帮我记一条通联""刚才和XX通了FM/FT8""加一条日志""查一下我的通联记录""QSL 卡还欠谁""帮我填 QSL 卡"时使用。
version: 1.0.0
author: 陆墨
tags:
  - hamlog
  - qso
  - qsl
  - radio
enabled: true
---

# HamLog 电台日志管理

通过 `agentType: "mcp"`、`service_name: "hamlog_adapter"` 调用，管理本地 HamLog（%APPDATA%/HamLog/Log.db）的 QSO/QSL 数据。

## 调用格式

```tool
{"agentType": "mcp", "service_name": "hamlog_adapter", "tool_name": "hamlog_qso_add", "callsign": "BG5ABC", "mode": "FM", "freq": "144.000"}
```

## 可用工具

| 工具 | 用途 | 关键参数 |
|------|------|------|
| `hamlog_qso_add` | 录入一条 QSO 通联记录 | `callsign`（必需，自动转大写）、`mode`（必需）、`qso_date`（选填，默认当天 UTC）、`freq`/`rst_sent`/`rst_rcvd`/`power`/`qth`/`remarks`（选填） |
| `hamlog_qso_search` | 搜索通联记录 | `callsign`/`since`/`until`/`mode` 均可选 |
| `hamlog_qsl_debts` | QSL 卡债清单 | `direction`: `owed`=我欠的 / `owing`=欠我的 / `all` |
| `hamlog_qsl_update` | 更新某条记录的 QSL 收发状态 | `qso_id`（先用 qso_search 查到）、`status`: `sent`/`received`/`pending` |
| `hamlog_card_content` | 生成 QSL 卡填写内容（content_lines 逐行抄卡） | `qso_id` |

## 使用说明

- **录入**：用户口头报通联信息（呼号、频率、模式等）时直接调 `hamlog_qso_add`；
  日期不说就用默认（当天 UTC），呼号会自动转大写，不用自己预处理。
- **日期格式**：统一 `YYYY-MM-DD`；中文"8月21日"这类工具也认，但能规范就规范。
- **需要 qso_id 时**：先 `hamlog_qso_search` 按呼号查，把返回的 `qso_id` 传给
  `hamlog_qsl_update` / `hamlog_card_content`。
- **录入成功后**：向用户复述确认（呼号/日期/模式），并提示数据已写入 HamLog 日志库；
  若 HamLog GUI 正开着且未显示新记录，重新打开即可刷新。
- **报错处理**：工具 fail-fast，数据库缺失/本台呼号未设置会明确报错，如实转告用户并按提示处理，不要自己编造数据重试。

## 示例

用户："刚和 BH8HJO 在 145.500 通了 FM，帮我记上"

```tool
{"agentType": "mcp", "service_name": "hamlog_adapter", "tool_name": "hamlog_qso_add", "callsign": "BH8HJO", "mode": "FM", "freq": "145.500"}
```

用户："查一下我上周的通联记录"

```tool
{"agentType": "mcp", "service_name": "hamlog_adapter", "tool_name": "hamlog_qso_search", "since": "2026-08-14", "until": "2026-08-20"}
```

用户："QSL 卡我还欠谁的？"

```tool
{"agentType": "mcp", "service_name": "hamlog_adapter", "tool_name": "hamlog_qsl_debts", "direction": "owed"}
```
