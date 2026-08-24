# 知识底座资料位置说明

本仓库原 `knowledge-base/`（学术冷门项目 + 非 LLM 拓广项目源码全集）已移至独立仓库托管，以减小本仓库体积。

## 资料新位置

完整的知识底座源码（academic / knowledge / infra / mcp）现存放于 GitHub：

- **GitHub 仓库**：`fe1iscurc0r/scratchpad-knowledge`
- **结构**：
  - `academic/` — 16 个学术冷门项目（SLICES、FEMcy、PyXtal、thermo、WaveBench 等）
  - `knowledge/` — 20 个非 LLM 拓广项目（siyuan、khoj、quartz、neosemantics、rdflib 等）
  - `infra/` — 基础设施（Kokoro-FastAPI、TTS-WebUI、kokoro-onnx、mcp-gateway-registry）
  - `mcp/` — 8 个 MCP server

## 获取方式

```bash
git clone https://github.com/fe1iscurc0r/scratchpad-knowledge.git
```

## 相关文档

- `INTEGRATION_PLAN.md` — 36 项目融合评估与时序计划
- `TRAE_PROMPT.md` — 知识底座预处理任务说明
