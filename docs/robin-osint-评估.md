# W68-04 robin 评估（AI 暗网 OSINT）

> 上游：github.com/apurvsinghgautam/robin · MIT · 6941★ · Python · 2026-08-25 活跃
> 落点：docs/robin-osint-评估.md · 勘察/评估

## 1. 项目定位

AI 驱动的暗网 OSINT 工具：用 LLM 精化查询、过滤暗网搜索引擎结果、给出调查摘要。Streamlit Web UI 交互式调查。

## 2. 架构拆解

- **模块化**：search / scrape / LLM 三工作流清晰分离。
- **多模型**：OpenAI / Claude / Gemini / Ollama / 任意 OpenAI 兼容 API。
- **交互**：对话式追问（不重跑搜索，从本次调查数据作答）、一键 pivot（从发现里生成新查询）。
- **部署**：Docker 推荐，隔离运行。

## 3. 与本仓对照

| 维度 | robin | 本仓 |
|---|---|---|
| OSINT | 暗网 OSINT（LLM 精化查询 + 摘要） | sentinel_intel（实体图谱）+ agent_osint + sentinel-osint-勘察报告 |
| 形态 | 独立 Streamlit 应用 | mcpserver 模块 |

## 4. 可落地借鉴点（≥3）

1. **LLM 在 OSINT 管线里的「查询精化 + 结果过滤 + 摘要」三段式**：可作为我们 OSINT 收集器的 LLM 增强层。
2. **对话式追问 + 一键 pivot**：从单次调查数据出发追问/pivot，而非每次重跑搜索——可作为 sentinel_intel 的调查交互范式。
3. **search/scrape/LLM 分离的模块化边界**：便于插拔新搜索引擎/模型/输出格式。

## 5. 许可裁定 + 结论

- **许可**：MIT → 可借鉴代码。
- **合规边界**：暗网/取证需合法授权（robin 自带 Disclaimer）。**结论**：参考「LLM 三段式 + 对话追问」设计并入 OSINT 收集器；暗网数据源访问默认关闭、按授权开启。
