# 峰谷双轨运维手册（peak / off-peak OPS）

> 工单 229 任务二产物 ｜ 2026-10-13 ｜ 适用：陆墨云服 + 本机 cron
> 配套脚本：[`tools/peak_switch.sh`](../tools/peak_switch.sh) ｜ 只读探针：`GET /admin/model_state`（工单 228）

## 0. 一句话

**工作日 09:00-12:00 与 14:00-18:00 走峰段模型（MiniMax-M3），其余所有时间走谷段模型
（deepseek-flash）；切换由 cron 调用 `peak_switch.sh` 完成。**

峰谷口径与 `apiserver/admin/router.py` 的 `PEAK_WINDOWS` **同源**，两边改动必须同时改——
这是唯一会被"改漏"的地方。

## 1. 峰谷表

| 时段 | 判定 | 模型 |
|---|---|---|
| 周一~周五 09:00-12:00 | 峰（**左闭右开**：09:00 含、12:00 不含） | `MiniMax-M3` |
| 周一~周五 14:00-18:00 | 峰（**左闭右开**：14:00 含、18:00 不含） | `MiniMax-M3` |
| 周一~周五 12:00-14:00 | 谷（午休） | `deepseek-flash` |
| 周一~周五 18:00-次日 09:00 | 谷 | `deepseek-flash` |
| **周六 / 周日 全天** | 谷 | `deepseek-flash` |

> 边界口径有回归测试兜底（`tests/test_peak_switch.py` 的 `test_peak_window_boundaries`，7 个边界点），
> 改口径先看那组断言。

## 2. 切换器

```sh
tools/peak_switch.sh                  # 按当前时间切换
tools/peak_switch.sh --dry-run        # 只打印将执行的命令（CI / 巡检可调用，不落盘）
tools/peak_switch.sh --now "1 09 30"  # 指定 <星期(1-7)> <时> <分>，排错 / 回归用
tools/peak_switch.sh --help
```

切换动作 = 依次执行 `hermes config set <key> <model>`，默认 key 为 `model.default`。
可覆盖的环境变量：`PEAK_MODEL` / `VALLEY_MODEL` / `CONFIG_KEYS` / `HERMES_BIN` / `DATE_BIN`。

退出码：`0` 成功或正常 dry-run；`2` 参数错误；其余为 `hermes` 退出码透传。

## 3. cron

> ⚠️ **本节为重建，未在本机复核。** 本机（Trae 侧）无 `~/.hermes/`、无 `crontab`、无 `hermes`
> 可执行文件——峰谷 cron 挂在**云服 / 沈遥侧**。下列 5 条按峰谷表反推，**请在云服上执行下面的
> 命令核对实际值**，与本文不一致时以云服为准并回填本文。

```sh
crontab -l | grep peak_switch          # 云服侧核对真值
```

| # | 计划 | 命令 | 作用 |
|---|---|---|---|
| 1 | `0 0 * * *` | `peak_switch.sh` | 日界回谷（也顺带覆盖周末全天） |
| 2 | `0 9 * * 1-5` | `peak_switch.sh` | 09:00 进峰 |
| 3 | `0 12 * * 1-5` | `peak_switch.sh` | 12:00 回谷 |
| 4 | `0 14 * * 1-5` | `peak_switch.sh` | 14:00 进峰 |
| 5 | `0 18 * * 1-5` | `peak_switch.sh` | 18:00 回谷 |

> 周末不需要单独条目：周五 18:00 切到谷段后，周末只有 `0 0` 那条会跑（仍是谷段），
> 到周一 09:00 才进峰——与峰谷表一致。

## 4. 出问题时的手动干预

**症状**：日志/对话里模型与预期时段不符，或某次切换没生效。

```sh
# 1) 看脚本会怎么判（不落盘）
tools/peak_switch.sh --dry-run

# 2) 直接手工切一步（绕过脚本，最快恢复）
hermes config set model.default deepseek-flash     # 谷段模型
hermes config set model.default MiniMax-M3         # 峰段模型

# 3) 确认现在到底生效的是什么
curl -s localhost:8000/admin/model_state | python -m json.tool    # 只读探针，工单 228

# 4) 复核 cron 是否还在
crontab -l | grep peak_switch

# 5) 手工补跑一次
tools/peak_switch.sh
```

`/admin/model_state` 的返回体带 `sources` 字段，会标明每个值的来源（仓内 config / hermes yaml /
peak log），排错时先看它——**它读不到任何一路也不会 500，只会降级返回**，所以"探针本身挂了"
不可能是模型不对的原因。

## 5. 模型名变更 SOP（本单第一个真实案例）

> 起因（沈遥侧 2026-10-10 实测）：DeepSeek 平台把老别名 `deepseek-chat` 静默 alias 到规范名
> `deepseek-flash`，但走老别名的请求返回 **HTTP 200 且 `choices[0].message.content == ""`**。
> 部分 SDK / 中间件把「200 但空 content」判为**错误**，用户侧看到的就是 400。
> 换成 `deepseek-flash` 后正常返回——**根因不是 zhipu key 失效，是模型别名路径**。

**遇到 400 / 空 content / "模型不可用" 时的排查顺序**：

1. **先看 model 别名，不要先怀疑 key。** 本次就是先怀疑 key，绕了一大圈。
   用同一 key 分别请求新旧两个 model 名，对比 `content` 是否为空。
2. 全仓扫一遍旧别名是不是到处都有：
   ```sh
   rg -n "deepseek-chat" --hidden -g '!node_modules' -g '!.venv'
   # 本机无 ripgrep 时（Trae 侧实测）：grep -rn --exclude-dir=.git -F "deepseek-chat" .
   ```
   落点分类：**代码/配置（改）** → **测试期望值（改）** → **文档现状描述（改）**；
   **带日期的历史实测记录（不改，改了就是伪造证据）** → **上游 `NEKO/**` 与第三方 `vendor/**`（不改）**
   → **工单正文（不改）**。
3. 改完**跑守卫测试**，别靠人工 grep 收尾：
   ```sh
   pytest tests/test_legacy_model_alias.py -q
   ```
   它扫 active 路径（范围与 `[tool.ruff] exclude` 对齐），命中即失败并逐条打印 `文件:行号:原文`；
   `ALLOWED_LEGACY_SITES` 是显式契约，允许"历史证据"保留旧字面量，新增落点会立刻红灯。
4. 全链路刷新（本次涉及）：`config` 的 `model.default` / `providers.<p>.model` / `fallback_providers`、
   `peak_switch.sh` 的两个模型名、各 cron job 的 snapshot。
5. 变更后 24h 内观察长尾 batch 的失败率（本次关注：论文 digest 那种 1168/1168 的长尾，
   若失败率 > 1% 考虑谷段也改走 M3——M3 思考链短但稳定）。

**同类风险**：任何 LLM 平台的 alias 漂移都**没有 CI 报警**。
`tests/test_provider_model_id.py`（工单 229 任务三）就是为这个加的——它真调各 provider 的
default 模型并比对返回的 `model` 字段，一旦 alias 漂移就报 `alias_diff`。

> **待办（旧别名清扫的收口）**：本仓 `docs/protocol-compat-audit-2026-10.md`（2026-10-08 实测对照表）
> 与 `mcpserver/rf_brain/SELFTEST.md`（2026-08-13 自测实录）**故意保留**旧字面量——它们是带日期的
> 历史证据，改了就是伪造。若将来要清理，请连同日期一起改，而不是只替换字符串。

## 6. 相关文件

| 文件 | 作用 |
|---|---|
| `tools/peak_switch.sh` | 峰谷切换器（本手册主角） |
| `tests/test_peak_switch.py` | 时段判定回归（6 时段 + 7 边界 + dry-run + 顺序 + 参数校验） |
| `apiserver/admin/router.py` | `PEAK_WINDOWS` 常量 + `GET /admin/model_state` 只读探针 |
| `tools/switch_llm_provider.py` | 手动换 provider / 换 model（带备份 + 原子写 + `--probe`） |
| `tests/test_legacy_model_alias.py` | 废弃别名清扫守卫 |
| `tests/test_provider_model_id.py` | 模型 ID 兼容矩阵（`@pytest.mark.live`，默认不跑） |
| `docs/glm-fallback-playbook.md` | GLM 兜底切换剧本（工单 210） |
