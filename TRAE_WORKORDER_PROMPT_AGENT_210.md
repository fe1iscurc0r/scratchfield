# 工单 210 · GLM 订阅到期应对手册 + 管线降级全集

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户 GLM coding 订阅约 2026-10-10 到期（两天窗口），本单做完整应对手册，不留模糊地带。已在用的 fallback 链（config.yaml 内置 deepseek-flash / MiniMax-M2.7）照旧，本单只补人工缺口。

## 任务一（P0）：全调用点审计——config.py × GLM × 16 个 provider

初勘已知 `system/config.py` 含 GLM 配置，但全系统有多少处直接调用 GLM 端点、各依赖哪段配置未知。

1. 用脚本扫描 `~/scratchpad/` 下所有 py 文件（排除 NEKO/frontend/.venv）：
   - 匹配模式：`open.bigmodel.cn` / `bigmodel` / `glm-` / `zhipu` / `GLM`（非注释、非字符串字面量），统计命中文件和命中行数
   - 输出表格：`文件 | 调用类型(URL/key/模型名) | 所在函数 | 是否经 config.py 间接调用`
2. 结论：标红"硬编码绕过 config.py 的直接调用"（若有），标黄"走 config.py 但只配了 GLM 无备选"
3. 报告落 `docs/glm-expiry-audit-2026-10.md`

## 任务二（P0）：降级决策树 + 切换脚本

当前 config.yaml fallback 链：zhipu（GLM）→ deepseek-flash → MiniMax-M2.7。本单补人工决策层：

1. 新建 `tools/switch_llm_provider.py`：
   - 输入：目标 provider 名称（`zhipu` / `deepseek` / `minimax`）
   - 操作：写 `~/.hermes/config.yaml` 里的 `model.provider` 和 `model.default` 字段（只改这两处，不动 API key），改前做备份（`~/.hermes/config.yaml.bak.{timestamp}`）
   - 验证：跑 `curl` 测连通性，200 打印 OK，超时/4xx 打印 FAIL 并 exit 1
2. 新建 `docs/glm-fallback-playbook.md` 一页手册：
   - 决策树：GLM 到期 → 自动 fallback deepseek → 若 deepseek 质量不行 → 切 MiniMax → 若 MiniMax 不可用 → 降级纯列表模式
   - 每步附切换命令（`python tools/switch_llm_provider.py deepseek`）
   - 重点：标出哪些 cron 任务（论文流水线等）依赖 GLM 特定能力（长上下文/function call），降级后哪些会降质

## 任务三（P1）：NEKO 上游 GLM 依赖盘存

NEKO 上游 Engine 的 `config/prompts/prompts_prologue.py` 等处若硬编码了 GLM 模型名而非走配置，在上游更新时可能沉默失效。

1. 扫 NEKO 源码（`~/scratchpad/NEKO/N.E.K.O/`）匹配 `glm` / `bigmodel` / `zhipu` 大小写不敏感
2. 输出命中表：`文件 | 行号 | 匹配内容 | 是否 prompt/模型名/URL`
3. 若是模型名字符串（不是注释）且没走配置：标注"待上游修复"，不自行改上游代码（NEKO 桥铁律：不吃上游改动）

## 验收
- [ ] 任务一：glm-expiry-audit 报告含调用点全表 + 硬编码红标 + 配置绕路黄标
- [ ] 任务二：switch_llm_provider.py 实跑验证（切到 deepseek 再切回 zhipu，两次都 OK）；降级 playbook 含决策树 + 每步命令
- [ ] 任务三：NEKO GLM 依赖表落盘，prompt 字符串标注"待上游"，不自行修改上游
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
