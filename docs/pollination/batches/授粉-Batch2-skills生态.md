# 授粉报告 Batch-2：Skills 生态（4 项）

> 日期：2026-08-22 晚 | 模式：API 直读 | 许可：agent-skills MIT / obsidian-skills MIT / guizang AGPL / nuwa MIT

## 一、addyosmani/agent-skills（89k★, MIT）— 生产级工程 skills

- **定位**：senior engineer 的 workflow/质量门/最佳实践编码成 skills
- **流程**：DEFINE → PLAN → BUILD → VERIFY → REVIEW（端到端）
- **价值**：和 superpowers 同赛道（WO-02 已授粉），但更偏"质量门"而非"方法论"
- **授粉建议**：与 superpowers 合并参考——它俩不冲突：superpowers 管流程分层，agent-skills 管每步质量门。现有 scratchpad skills/ 可借鉴它的 VERIFY/REVIEW 检查单结构
- **落点**：不单独授粉，并入 WO-02 的 superpowers 报告做对照补充

## 二、kepano/obsidian-skills（47k★, MIT）— Obsidian Agent Skills

- **定位**：Agent Skills 规范（agentskills.io）的 Obsidian 技能集
- **关键**：**遵循 Agent Skills 规范**——Claude Code/Codex/OpenCode 通用
- **价值**：我们 obsidian 技能（note-taking/obsidian）可对照升级；规范本身值得抄（跨 agent 兼容标准）
- **授粉建议**：读一遍 Agent Skills 规范 → 对照 scratchpad skills/ 格式是否兼容（若兼容则未来 skills 可跨 agent 用）
- **落点**：format 对齐评估（轻量，文档类）

## 三、op7418/guizang-ppt-skill（24k★, AGPL）— 网页 PPT 技能

- **定位**：HTML 网页 PPT / 配图 / 封面生成（真格 Token Grant 资助）
- **价值**：Lumo/陆墨汇报场景直接可用（网页 PPT 免 PPT 软件）
- **AGPL 注意**：AGPL 可并入 AGPL 主仓（主仓协议就是 AGPL）✅
- **授粉建议**：直接 clone 评估，作为 Lumo 的汇报输出格式（HTML deck 比 .pptx 轻）
- **落点**：skills/ 新增 guizang-ppt（若 Lumo 需要汇报能力）

## 四、alchaincyf/nuwa-skill（31k★, MIT）— 女娲「人设蒸馏」【同源修正】

- **定位**：「你想蒸馏的下一个员工，何必是同事」——蒸馏任何人的思维方式
- **兼容**：Agent Skills 标准 + 多运行时（Claude Code/Codex/Cursor/OpenClaw/**Hermes**）
- **🔴 修正（2026-08-22 晚实查）**：本地 `huashu-nvwa` 的 examples（andrej-karpathy/elon-musk/feynman/ilya-sutskever/mrbeast/munger/naval/paul-graham/steve-jobs/sun-yuchen/taleb/x-mastery-mentor/zhangxuefeng）与 nuwa-skill 的 examples **完全重合**——**它是我们的上游，我们是它的 fork + 本地扩展**（自研了 focus-effect/social-engineering/uav-systems 系列）
- **上游新特性（本地可能缺，待同步）**：
  - `references/extraction-framework.md` / `fidelity-scorecard.md` / `skill-template.md` — 蒸馏框架/保真度评分/模板
  - `scripts/`：download_subtitles.sh / merge_research.py / quality_check.py / srt_to_transcript.py — 调研流水线脚本
  - 最新 commit：模板输出规范优化（未表态主题标推断 + 关键引用可分辨，Issue #65 双盲实测）
- **授粉建议**：**同步上游新特性**（FIDELITY 评分 + scripts 流水线）→ 增强本地 huashu-nvwa；已有 selfmade 系列保留
- **落点**：huashu-nvwa 同步增强（上游 MIT 可直接抄）

## 五、Batch-2 行动项

1. **nuwa-skill 模板对照**（最高价值，同款竞品直接抄格式）→ 增强 huashu-nvwa
2. **guizang-ppt** → Lumo 汇报格式评估（AGPL 兼容）
3. **obsidian-skills 规范对齐** → skills 跨 agent 兼容（轻量）
4. agent-skills → 并入 WO-02 参考，不单独做

---
*注：本批 4 项都是 skills 生态，与已有 huashu-nvwa / obsidian 技能直接相关，授粉成本低收益直接*
