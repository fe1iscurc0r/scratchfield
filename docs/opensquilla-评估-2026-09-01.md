# TB06 OpenSquilla SquillaRouter 评估报告

> 2026-09-01 · 智能体 53 · 来源：`github.com/opensquilla/opensquilla`
> 目标：评估 SquillaRouter 四通道冷启动路由（准入过滤/需求构造/风险定价/能力匹配 + LightGBM），
> 对论文流水线 digest/授粉环节做成本优化设计。
> 阅读文件：`engine/router_decision.py`、`router_tiers.py`、`engine/route_plan.py`、
> `engine/routing/policy.py`、`engine/routing/heuristic.py`、`engine/capacity_admission.py`、
> `engine/pricing.py`、`engine/steps/squilla_router.py`。

## 1. 架构拆解

SquillaRouter 是**两段式**路由：一个 ML 分类器定初判，一组命名的后分类器规则阶段做修正，
最后固化成一个不可变的路由决策。

```
消息 turn
  │ Step 2 squilla_router：LightGBM（"V4 Phase 3 ML runtime"）分类复杂度 → route class c0~c3
  │   + 2 级 ThinkingController / PromptController
  ▼
RoutingPolicyEngine（7 个命名阶段，按固定顺序）
  confidence_gate   —— 低置信度回落到默认 tier（高于默认 tier 再扣 0.05 折扣）
  complaint_upgrade —— 含投诉词升级 tier
  anti_downgrade    —— KV-cache 窗口内不低于上一轮 tier（省重复预填充）
  capability_gate   —— 目录明确"模型不能服务"（缺 vision / 上下文超限）→ 向上走 tier
  bind              —— 记录路由轨迹，绑定最终 tier 的模型，调和 thinking/prompt 策略
  large_context_floor —— 大材料上下文硬 floor 到 c2/c3
  provider_mismatch —— 默认 flag-only；"veto" 时重绑到最近可执行 tier
  ▼
不可变 RoutePlan（tier/provider/model/capabilities/frozen candidate snapshot）
  ▼
router_decision 事件（tier/probs/confidence/savings_pct/fallback …）→ 遥测与成本归因
```

**四通道**对应关系：

| 通道 | 落点文件 | 机制 |
|---|---|---|
| 准入过滤 | `capacity_admission.py` / `channels/admission.py` | fail-closed：目录上下文窗口证明装不下 → 拒绝/降级 |
| 需求构造 | `route_plan.py` RouteCapabilitySnapshot | context_window / vision / tools / streaming / reasoning |
| 风险定价 | `pricing.py` PricingCache + `lookup_price` | OpenRouter 每 token 价（1h TTL 缓存）做成本估计 |
| 能力匹配 | `routing/policy.py::capability_gate` | 缺能力向上走 tier，宁可贵也不误路由 |

**LightGBM**：`squilla_router` 步骤的"bundled V4 Phase 3 ML runtime"分类器（`router_runtime_diagnostics`
里对 `lib_lightgbm` / macOS `libomp` 的运行时诊断），负责把复杂度映射到 route class。

**关键设计原则**（值得照搬的三点）：
1. **路由只决定一次**：`RoutePlan` 不可变，provider 重试/selector failover 是物理执行细节，
   不再产生新的路由决策 → 成本归因与审计干净。
2. **单一事实源**：`router_tiers.py` 集中 tier 别名（t0~t3 → c0~c3）、ensemble selection mode、
   provider ownership role，各消费方不再各自 `.get("model")` 拼默认值。
3. **ML 不可用时的诚实降级**：`routing/heuristic.py` 用 surface features（长度/代码块/附件）
   无依赖分类，且置信度故意压在 0.55–0.60，避免静默全部回落到默认 tier。

## 2. 对论文流水线 digest/授粉 的可落地借鉴点（≥3）

**借鉴 1：两段式「分类器 + 后分类器规则」，冷启动用 surface-feature 启发式。**
digest/授粉流水线每天要决定"每篇 digest 走哪条线（R/M/K/S/A）、用哪档模型/流程"。
照搬 SquillaRouter：先一个轻量分类器给初判（可先用规则版），再叠一组命名规则阶段
（置信度门控 / 领域地板 / 能力匹配 / 防降级）做修正。冷启动（无标注、无校准数据）时
直接用 `heuristic.py` 的 surface-feature 启发式（标题关键词、篇幅、模态），不要
静默全部走"最全流程"——那是最贵的降级。

**借鉴 2：能力匹配 fail-closed + 大材料 floor，直接省钱。**
digest 有长短之分、授粉点有跨模态（文本/频谱/材料图）。用 `capability_gate` 语义：
模型/流程明确"处理不了"（超上下文、缺多模态能力）时向上走档或拒收，而不是硬塞；
长 digest（大材料上下文）floor 到高成本档。配合 `pricing.py` 式的每 token 价缓存，
每个 digest 的吞吐成本可实时估计、可归因。

**借鉴 3：不可变路由计划 + append-only 成本记录。**
把"这篇 digest 用哪档模型/流程"固化成一次不可变决策，物理重试不产生新决策；
成本/省额（`savings_pct`、`tier_savings`）随决策事件一并落账。这样第 N 批 digest
的成本、命中率、回退率都可回溯，支撑"授粉命中率 vs 成本"的 A/B 与预算审批。

**借鉴 4（附加）：置信度折扣 + 校准偏置，防低置信度越级到贵档。**
高于默认档的路由额外扣 0.05 置信度折扣；`calibration.py` 的 `apply_bias` /
`effective_threshold` 用历史真实结果修系统性路由偏差。digest 流水线同样需要
"分类器概率"被校准后再决定走不走贵档，避免越级。

## 3. 结论

SquillaRouter 的"两段式路由 + 后分类器规则阶段 + 不可变决策 + fail-closed 能力匹配 +
ML 降级启发式"是一套成熟、可审计、面向成本的路由范式。论文 digest/授粉环节的
"线-模型-成本"路由可直接复用其架构骨架，冷启动阶段先用 `heuristic.py` 式无依赖
启发式，省去"全部走最贵流程"的浪费。无阻塞。
