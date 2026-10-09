# 工单 216 · 跨领域协议兼容审计——六条线的"未适配嫌疑"排查

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户问"其他领域有没有协议不兼容/未适配的嫌疑"。沈遥初勘发现六条嫌疑线（LLM 供应商 / 渠道 / 科学数据格式 / 遥测 / 存储 / 语音），本单做系统性审计。**先审计后立项，本单不实装。**

## 初勘发现的六条嫌疑线（按风险排序）

| # | 领域 | 嫌疑 | 初勘证据 |
|---|---|---|---|
| 1 | LLM 供应商 | `_real_providers` 硬编码 5 家（openai/deepseek/gemini/openrouter/anthropic），**zhipu/minimax 不在表内**——走 base_url 推断的兼容路径，GLM 到期切换时可能踩坑 | `llm_service.py:257` |
| 2 | 消息渠道 | `channels/` 只有 Webhook + Telegram 两个实现，**QQ/微信不在 apiserver 侧**（NEKO 插件侧有），ChannelMessage 抽象已备但没接 | `apiserver/channels/__init__.py:5` 自注 |
| 3 | 科学数据格式 | 材料线只有 SMILES（指纹/图编码），**CIF/PDB/xyz 原子坐标格式零适配**——做分子模拟/晶体结构时进不去 | `material_science/symbolic/encode_eval.py` |
| 4 | 遥测协议 | 自研 telemetry JSON，**OTLP/OpenTelemetry 零适配**——想接 Grafana/Jaeger 等标准观测栈时无出口 | grep 全仓无 otel 命中 |
| 5 | 存储/同步 | http_share 手工中转（18188），**WebDAV/S3/rsync 零适配**——大文件分发全靠手工 curl | grep 无 webdav/s3 客户端 |
| 6 | 语音管线 | voice_mcp_bidi 存在但 realtime 协议细节未盘（OpenAI Realtime API 的 opus/pcm16/input_audio 报文格式适配深度未知） | `voice_mcp_bidi/` |

## 任务一（P0）：六线审计矩阵

对每条嫌疑线出审计条目，格式统一：

```
| 线 | 现状 | 标准协议/格式 | 差距 | 影响 | 建议动作 | 优先级 |
```

1. **LLM 供应商表**（最高优）：
   - 实测验证 zhipu（GLM coding 端点）和 minimax 走当前 base_url 推断路径是否正常工作（构造请求实测，不猜）
   - 若踩坑：改法是加进 `_real_providers` 还是抽象 provider 注册表（参考 Hermes config.yaml 的 providers 结构），出方案不动手
2. **渠道矩阵**：QQ（QQbot）/微信（weixin iLink）/Telegram/Webhook 四渠道，各自在 NEKO 插件侧还是 apiserver 侧、ChannelMessage 抽象能否覆盖（不能覆盖的差什么字段）
3. **科学数据格式**：列材料科研常用格式清单（CIF/PDB/xyz/MOL2/SDF/VASP），逐个标注仓内有无读写器；给最小适配集建议（木质素 NPs 工作流最可能用到的 3 个）
4. **OTLP**：自研 telemetry 的字段映射到 OTLP span/metric 语义的可行性一段话
5. **存储**：http_share 现状 + 若要自动分发（Gitee 不稳线）WebDAV/S3 哪个成本最低
6. **语音**：盘 voice_mcp_bidi 对 OpenAI Realtime 报文格式的适配深度（全/半/仅文本）

## 任务二（P1）：协议适配优先级评审

1. 汇总六线 → `docs/protocol-compat-audit-2026-10.md`：
   - 按"用户近期路线图触碰概率"排序：GLM 切换（10-10 就到）> 渠道统一 > 科学格式（材料线本科数据）> 其他
   - 每线给三选一：立即适配 / 接口预留（同 ROS 线定调：留 adapter 不装依赖）/ 不动
2. **与 ROS 线同构的接口预留原则**复用到 LLM provider 注册表：若选预留，接口签名草案直接写进审计报告

## 验收
- [ ] 任务一：六线审计矩阵每行含实测/实查证据（LLM 线必须真实发请求验证，不接受纯代码推断）；科学格式逐格式标注
- [ ] 任务二：protocol-compat-audit 报告落盘，每线三选一结论 + 排序理由；LLM 线给 provider 注册表接口草案
- [ ] 全程零依赖引入；CI 绿
