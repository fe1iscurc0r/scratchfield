---
name: naga_control
description: Naga 自身控制能力。暂停/恢复语音和Live2D、切换模型/角色、管理会话/技能、控制音乐播放、启停旅行等。当用户要求控制自身功能时使用。
version: 1.0.0
author: Naga Team
tags:
  - control
  - voice
  - live2d
  - model
  - music
  - self-management
enabled: true
---

# Naga 自身控制

通过 `agentType: "naga_control"` 调用，直接控制 Naga 自身的运行状态和配置。

## 调用格式

```tool
{"agentType": "naga_control", "action": "动作名", "params": {参数}}
```

## 可用动作

| 动作 | 用途 | 参数 |
|------|------|------|
| `get_config` | 读取配置 | `section?`(string，如 "api"、"system"、"tts") |
| `update_config` | 修改配置并持久化 | `config`(object，如 {"api": {"temperature": 0.5}}) |
| `get_status` | 获取系统状态 | 无 |
| `toggle_voice` | 暂停/恢复语音 | `enabled`(bool) — 运行时暂停，不改设置 |
| `toggle_live2d` | 暂停/恢复Live2D | `enabled`(bool) — 运行时暂停，不改设置 |
| `set_model` | 切换LLM模型 | `model`(string); `base_url?`, `api_key?` |
| `list_characters` | 列出可用角色 | 无 |
| `switch_character` | 切换角色 | `character`(string) |
| `list_sessions` | 列出会话 | `limit?`(int) |
| `clear_session` | 清空会话 | `session_id`(string) |
| `list_skills` | 列出技能 | 无 |
| `toggle_skill` | 启停技能 | `name`(string), `enabled`(bool) |
| `list_mcp_services` | 列出MCP服务 | 无 |
| `play_music` | 控制音乐播放 | `action`("play"/"pause"/"next"/"prev"/"toggle"); `track?`(文件名) |
| `start_travel` | 启动旅行 | `time_limit?`, `credit_limit?` |
| `stop_travel` | 停止旅行 | 无 |
| `get_memory_stats` | 记忆统计 | 无 |
| `send_notification` | 发送通知 | `message`(string), `type?`("info"/"warning"/"error") |

## 重要说明

- `toggle_voice` / `toggle_live2d` 是**运行时暂停/恢复**，不修改用户设置。只有用户明确要求"修改设置"时才用 `update_config`。
- `play_music` 的 `action` 参数：`play` 播放（可指定 track 文件名）、`pause` 暂停、`next` 下一首、`prev` 上一首、`toggle` 切换播放/暂停。

## 示例

暂停语音:
```tool
{"agentType": "naga_control", "action": "toggle_voice", "params": {"enabled": false}}
```

查看当前模型:
```tool
{"agentType": "naga_control", "action": "get_config", "params": {"section": "api"}}
```

修改温度:
```tool
{"agentType": "naga_control", "action": "update_config", "params": {"config": {"api": {"temperature": 0.5}}}}
```

随机播放音乐:
```tool
{"agentType": "naga_control", "action": "play_music", "params": {"action": "play"}}
```

播放指定曲目:
```tool
{"agentType": "naga_control", "action": "play_music", "params": {"action": "play", "track": "8.日常的小曲.mp3"}}
```
