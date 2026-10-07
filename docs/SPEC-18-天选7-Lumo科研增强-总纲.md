# SPEC-16 天选7 Lumo 科研增强 · 总纲 · v1

> 状态：待施工（2026-08-25 用户拍板：六模块全要，写 SPEC）
> 用途：天选7 Pro（RTX 5060 8GB / Windows / lumo 桌面端）从"AI 伴侣"升级为**材料学科研操作系统**——实验记录、材料模型、文献、电台、数据工具台
> 读者：Trae（天选7）/ 沈遥 / 陆墨
> 依据：SPEC-15（身份层，本 SPEC 是能力层）；Old-Target-New-Model-Plan-v1.md（靶子 A/B/D）；skills/lumo-hamlog-log + mcpserver/adapters/hamlog_adapter.py（已授粉）；skills/experimental-design（DOE，已入 skills 未注册 manifest）；iu2frl-civ 调研（phone-mobile-hub）；用户确认：Ollama 已装、OB(Obsidian) 已有

## 〇、一句话定位

**天选7 = 科研主力机**：RTX 5060 跑材料模型（Ollama 已装），Obsidian 当实验记录本（已有），lumo 把"文献 → 实验设计 → 记录 → 数据 → 模型 → 报告"串成闭环。所有模块复用已有授粉资产，不重复造轮子。

## 一、模块总览（六模块，三优先级）

| 模块 | 内容 | 优先级 | 复用现状 |
|---|---|---|---|
| A | ELN 实验记录本（Obsidian-based） | P0 | OB 已有；experimental-design skill（设计→记录闭环） |
| B | 材料模型算力（Ollama，跑材料 ML 而非聊天） | P0 | Ollama 已装（天选7）；Old-Target 靶子 B（maml+RF/BP） |
| C | 文献管理器（条目/DOI/笔记） | P1 | Old-Target 靶子 D（PDF→MD）；云服论文流水线 |
| D | 705 控制面板 + 电子日志（hamlog 续写） | P1 | hamlog_adapter 已实现（QSO/QSL）；iu2frl-civ CI-V 方案 |
| E | 实验数据工具台（TGA/DSC/XRD 导入+绘图） | P1 | 天选7 Python 算力；matplotlib |
| F | 语音实验记录（边做边说→ASR→ELN） | P2 | Qwen ASR 已有（NEKO 身体层） |

**数据流（闭环）**：
```
文献(靶子A/D) → 结构化实验数据库 → ELN 实验记录本(OB)
     ↑                                    ↓
材料模型预测(Ollama/B) ← 历史数据         实验数据工具台(TGA/DSC/XRD)
     ↓                                    ↓
实验设计(DOE) → 新实验 → ELN ← 语音记录(F) → 报告导出
```

## 二、模块设计

### A. ELN 实验记录本（Obsidian-based）
- **形态**：Obsidian vault（`~/LumoVault/` 或既有 vault）建 `experiments/` 目录 + 模板；lumo 前端加 ELN 视图（列出实验、搜索、打开/新建、导出报告）
- **模板字段**：日期 / 课题 / 目的 / 药品与用量 / 条件（温度/时间/气氛）/ 结果 / 照片(附件) / 结论 / 关联文献
- **打通**：experimental-design skill 产出设计 → 一键生成 ELN 记录模板（设计即记录起点）
- **导出**：实验报告 Markdown → PDF/Word（实验课报告直接交）
- **验收**：lumo ELN 视图列出/新建实验；模板字段齐全；导出报告可用；DOE 设计→记录模板一键生成

### B. 材料模型算力（Ollama）
- **定位修正**：不是 LLM 聊天逃生舱，是**材料 ML 推理/训练**（用户拍板）。Ollama 已装天选7
- **靶子 B 落地**：生物质材料 ML 预测——碳化条件（温度/时间/升温速率）× 原料特性 → 产物性质（产率/比表面/热值）；maml + 随机森林/BP
- **数据源**：ELN 历史数据 + 靶子 A 文献提取数据（结构化实验数据库）
- **形态**：Python 训练/推理脚本（天选7 本地跑，RTX 5060 加速）；结果回写 ELN；Ollama 负责辅助（数据解读/报告润色，可选）
- **验收**：一个真实预测跑通（历史数据训练 → 新条件预测）；预测结果可回写 ELN 实验记录

### C. 文献管理器
- **形态**：lumo 文献视图（条目列表：标题/DOI/期刊/年份/笔记/标签），本地 SQLite
- **打通**：云服论文流水线（采集→精读）产物同步进天选7 文献库；靶子 D（PDF→MD）本地入库
- **关联**：文献 ↔ ELN 实验（记录里引文献）
- **验收**：文献条目增删改查；DOI 导入；云服流水线同步入口；实验记录可引文献

### D. 705 控制面板 + 电子日志（hamlog 续写）
- **复用**：hamlog_adapter 已实现（QSO/QSL 管理，Log.db）；lumo-hamlog-log skill 已注册
- **新增**：705 控制面板（CI-V USB 直连天选7，调频率/模式/PTT，参考 iu2frl-civ 已验证方案）；通联完成 → 一键进 hamlog
- **验收**：705 面板可调频率/PTT；通联记录一键入 hamlog；QSL 卡债查询（已有）

### E. 实验数据工具台
- **形态**：lumo 数据视图——导入 TGA/DSC/XRD 原始数据（CSV/TXT）→ 预处理 → 绘图（matplotlib）→ 图表进 ELN
- **验收**：三类数据导入模板各一；绘图输出 PNG 入 ELN 附件；常见预处理（基线扣除/归一化）可用

### F. 语音实验记录（P2，后置）
- 边做实验边说 → Qwen ASR → 文本 → 自动生成/追加 ELN 记录
- **验收**：语音输入生成 ELN 草稿；可编辑后入库

## 三、实施顺序

P0（A+B）→ P1（C+D+E）→ P2（F）。A 是底座（记录本），B 吃 A 的数据；C/E 与 A 打通；D 独立可并行；F 最后。

## 四、工单划分建议（天选7 Trae）

| 线 | 工单 | 内容 |
|---|---|---|
| V | V-01/V-02 | ELN 视图 + 模板/导出（A）；实验数据工具台（E） |
| W | W-01/W-02 | 材料模型管线（B）；文献管理器（C） |
| X | X-01/X-02 | 705 面板 + hamlog 联动（D）；语音记录（F） |

三线独立可并行（V/W 依赖 A 的 vault 结构约定，X 完全独立）。

## 五、验收标准（总）

1. ELN 视图可用：列实验/新建/导出报告（A）
2. 材料模型一个真实预测跑通，结果回写 ELN（B）
3. 文献条目 + 云服同步入口（C）
4. 705 面板调频/PTT + 通联进 hamlog（D）
5. TGA/DSC/XRD 导入绘图入 ELN（E）
6. 语音生成 ELN 草稿（F）

## 六、提交规范

- 本 SPEC 进 scratchpad 仓库（工单分支）；施工产物走天选7 侧 trae/agent-* 分支（用户转交）
- 天选7 本地验证优先（npm run dev / python 直接跑），真机（705/实验数据）验证点列明
- 发现假设不成立 → 回填本 SPEC

---

*制定：沈遥（Hermes）· 2026-08-25*
*依据：SPEC-Writing-Standard-v2 + Old-Target-New-Model-Plan + 已授粉 hamlog/experimental-design + 用户 8-25 拍板*
