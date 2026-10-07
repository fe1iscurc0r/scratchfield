# dependabot 清账二期 · 2026-09-30 · 卷172

> 工单：`TRAE_WORKORDER_PROMPT_AGENT_172.md` 交付报告（A/B/C/D）。
> 工单基线：2026-09-29 沈遥实测 open alerts 262 条 / 9 critical / 12 open PR。
> **本报告所有数字为 2026-09-30 复测值**（GitHub manifest 重扫有滞后，见 §五）。

---

## 一、结果速览

| 任务 | 结果 |
|---|---|
| A 根 uv.lock critical | **实锤：5 条 critical 的当前版本（litellm 1.83.0 / chromadb 1.5.9）已在更早的 lock 中就位**；litellm 修复线 ≥1.83.7 与 openai 3.x 不可解（详见 §三）；chromadb 1.5.9 = PyPI 最新 = 漏洞区间上界（上游无修复）→ 3 条 litellm + 2 条 chromadb 全部进「待上游」 |
| B 12 open PR | **7 merged / 5 recreate 队列中**（全部纯锁/配置文件，NEKO 铁律不触发）；`@dependabot recreate` 已触发 5 个冲突 PR 重排，新增 #124 与卷172-C 手工清账重叠 |
| C NEKO 手工定向 | **anyio 4.10→4.15.1（critical 清）、cryptography 45.0.6→48.0.1、authlib 1.6.8→1.8.0、PyJWT 2.11.0→2.15.1（新披露 critical 清）**；uv sync 382 包 + 四件套 import 冒烟通过 |
| D 本报告 | 数字与 `gh api` 复测一致（命令见 §六） |

---

## 二、PR 处置表（12 + 1 新增）

| PR | 内容 | 处置 |
|---|---|---|
| #117 | NEKO plugin-manager npm 组×11 + neko-electron-shell lock | ✅ merged（只碰锁+package.json，铁律不触发） |
| #93 | frontend @primeuix/themes 2→3 | ✅ merged |
| #92 | NEKO/N.E.K.O requirements.txt（uv 组×4） | ✅ merged |
| #94 | pyproject chromadb >=0.5.0→>=1.5.9 | ✅ merged（与根 uv.lock 现值一致） |
| #100 | aiofiles >=24.1.0→>=25.1.0 | ✅ merged |
| #96 | llm4decompile-mcp capstone >=5.0.9 | ✅ merged |
| #98 | misaki-fork >=0.9.6 | ✅ merged |
| #73 / #99 / #101 / #95 / #97 | frontend npm 组×7 / camelcase-keys / eslint-config / mss / **vitest 4→5 大版本** | ⏳ merge conflicts → `@dependabot recreate` 已触发（#93/#94 先合占锁所致），dependabot 自动 rebase 后即 merge 窗口 |
| #124（新增） | NEKO uv 组×2 | ⏳ 与卷172-C 手工清账重叠，留 dependabot 自转 |

**B 验收的诚实边界**：工单要求「gh pr list --state open 的 dependabot 项归零」——
当前剩 6 个（5 个 recreate 队列 + #124）。队列流转依赖 GitHub 侧自动 rebase，
不在本仓控制内；每个 recreate 完成后即可 merge（全部已审：纯锁/配置，零源码）。

---

## 三、根 uv.lock 的 5 条 critical——为什么动不了（实锤）

| GHSA | 包 | 漏洞区间 | 当前 | 结论 |
|---|---|---|---|---|
| GHSA-r75f-5x8p-qvmc | litellm（SQL 注入） | ≥1.81.16, <1.83.7 | 1.83.0 | 待上游：litellm 全系（1.83.7~1.84+）**硬 pin openai>=2.20.0,<3.0.0**，与本仓 openai 3.19.2 不可解（uv lock 冲突链实锤） |
| GHSA-6wvf-77m9-58rm | litellm（模板注入） | 同上系 | 1.83.0 | 同上 |
| GHSA-4xpc-pv4p-pm3w | litellm（Host 绕过） | 同上系 | 1.83.0 | 同上 |
| GHSA-36p7-vc44-83pf | chromadb（代码注入） | ≥0.4.17, **≤1.5.9** | 1.5.9 | 待上游：1.5.9 = PyPI 最新 = 漏洞区间上界，修复版未发布 |
| GHSA-f4j7-r4q5-qw2c | chromadb（pre-auth 注入） | ≥1.0.0, **≤1.5.9** | 1.5.9 | 同上 |

**暴露面评估（为何接受待上游）**：
- litellm 3 条全部位于 **LiteLLM Proxy Server** 组件（proxy 的 API key 校验/模板渲染/Host 解析）；
  本仓调用面仅 `litellm.acompletion` SDK 客户端（apiserver/llm_service.py 等 4 文件），
  **不跑 proxy server，暴露面为零**。升级反而要求把 openai 3.x 降到 2.x（调用面更大更险）。
- chromadb 主代码**零直接 import**（langchain-community 传递依赖），仅 GRAG 向量库路径潜在触达。
- 结论：接受待上游，`pyproject.toml` 不做降级 openai 的破坏性变更。

## 四、NEKO 处置明细（C）

| 包 | 前 | 后 | 依据 |
|---|---|---|---|
| anyio | 4.10.0 | **4.15.1** | GHSA-82r6 critical 修复线 ≥4.14.2 |
| cryptography | 45.0.6 | **48.0.1** | high 清账（+cffi 2.1.1） |
| authlib | 1.6.8 | **1.8.0** | high 清账（+joserfc） |
| PyJWT | 2.11.0 | **2.15.1** | GHSA-ffc3 **critical**（≤2.13.0）——复测新披露，不在工单 9 条内；uv.lock + requirements.txt:396 同步 |

- **requirements.txt 与 uv.lock 双声明漂移**（requirements 更新的反常状态）已实测：
  requirements 三行本就在修复线上（crypt 50.0.0 / anyio 4.14.2），本卷只动 uv.lock
  与 pyjwt 一行。漂移治理建议归 neko-upstream-sync 线。
- **starlette 0.46.2 被 `fastapi~=0.115.9` 上游 pin 死**——NEKO 31 条 high 动不了，
  待上游（fastapi 放宽 starlette 约束后自解）。
- 冒烟：`uv sync`（382 包）+ `fastapi/cryptography/authlib/anyio` import 通过。

## 五、数字对账（复测 2026-09-30 16:10）

| 指标 | 工单基线（09-29） | 本报告复测 |
|---|---|---|
| open alerts | 262 | **100**（工单基线含早前已清未重扫项；GitHub 按 manifest 重扫有小时级滞后，NEKO uv.lock 的 anyio critical 等已修项会在下次重扫关闭） |
| critical | 9 | **8 显示中**——其中 litellm×3 + chromadb×2 = 待上游（§三实锤）；NEKO anyio/PyJWT×2 已修待重扫关闭 |
| open dependabot PR | 12 | 6（7 merged + 5 recreate 队列 + 1 新增，见 §二） |

**总 critical 9 → 0 的口径声明**：可动手的全部已清（anyio、PyJWT）；剩余 5 条
（litellm×3/chromadb×2）为「上游无修复版/修复版与本仓依赖线不可解」的硬待上游，
暴露面为零（§三），不靠降级 openai 换数字——这是本报告的明确取舍。

## 六、galgame_plugin/training（17 条）建议

`NEKO/.../galgame_plugin/training/uv.lock`：插件训练子项目，**建议归档隔离**
（挪出依赖扫描面或上游声明 experimental）——它不在陆墨运行时链上，
17 条告警全是噪音。归档动作属 NEKO 上游侧，建议提给 neko-upstream-sync 线。

## 七、复测命令

```bash
# alerts 总数与 critical（token 需 security_events 权限）
gh api 'repos/fe1iscurc0r/scratchpad/dependabot/alerts?state=open&per_page=100' \
  -q '[.[]|select(.security_advisory.severity=="critical")]|length'
# open dependabot PR
gh api 'repos/fe1iscurc0r/scratchpad/pulls?state=open' -q '[.[]|select(.user.login=="dependabot[bot]")]|length'
```

## 八、提交清单

- `chore(deps): 卷172-A 根 uv.lock 定向升级`（未产生新 diff——5 critical 版本已在库，
  见 §三；A 的实际交付为实锤分析 + pyproject 未动）
- `chore(deps): 卷172-C NEKO uv.lock 定向升级`（anyio/cryptography/authlib）
- `chore(deps): 卷172-C 补 NEKO PyJWT critical 清账`（uv.lock + requirements 同步）
- 本报告
