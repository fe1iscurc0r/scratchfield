# W69-05 BiliSum 评估（B站/视频 AI 摘要知识库）

> 上游：lycohana/BiliSum · MIT · ~549★ · 2026-04 · Python · 活跃
> 定位：Bilibili/YouTube/本地视频 AI 视频摘要 + 知识库
> 结论：**并入 bilibili skill 的摘要能力**（MIT 可融合，补本仓 bilibili-video skill 的摘要短板）

## 1. 项目定位与架构

BiliSum 做「视频 → AI 摘要 → 知识库」闭环：视频源（B站/YouTube/本地）→ 字幕/音轨提取 →
LLM 摘要 → 结构化知识库（可检索）。核心价值是视频长内容的「可检索化」——把不可检索的视频
转成可检索的文本摘要 + 时间戳锚点。

## 2. 与本仓对照

| 维度 | BiliSum | 本仓 bilibili-video skill / youtube-content skill |
|------|---------|--------------------------------------------------|
| 视频获取 | 支持 B站/YouTube/本地 | 各自 skill 已有获取能力 |
| 字幕提取 | 有 | 部分 |
| **AI 摘要** | **有（LLM 摘要管线）** | **弱/缺** |
| 知识库化 | 有 | 无 |

本仓 bilibili-video / youtube-content skill 偏「获取/播放」，**缺「摘要 + 知识库化」**；BiliSum
恰好补这块。

## 3. 可落地借鉴点（≥3）

1. **视频摘要管线**：字幕提取 → 分段 → LLM 摘要 → 时间戳锚点，是「视频可检索化」的通用套路。
2. **摘要知识库化**：把摘要 + 时间戳存成可检索条目（按视频/分P/时间段），供后续问答定位到具体片段。
3. **多源统一抽象**：B站/YouTube/本地统一成「视频源 → 摘要」接口，本仓两个 skill 可统一到一个摘要后端。

## 4. 许可裁定与结论

- **许可**：MIT，**可融合**。
- **结论**：**并入 bilibili skill 的摘要能力**。不独立建新项目——把 BiliSum 的「摘要 + 知识库化」思路并入现有 bilibili-video skill（并复用到 youtube-content），补上「看视频 → 摘要 → 检索」闭环，比单独维护一个 BiliSum 副本更符合本仓 skill 形态。
