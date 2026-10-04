# W72 卷评估报告 + 执行清单（npm / crates.io / 技术雷达 10 项）

> 智能体 72 · 勘察/评估 · 10 项（W72-01~10）
> 纪律：评估报告含项目定位 + 架构拆解 + 与本仓对照 + ≥3 可落地借鉴点 + 许可裁定。

## 方法说明

- 来源：TRAE_WORKORDER_PROMPT_AGENT_72.md（上游 URL/定位/落点已给）+ 领域常识。
- 上游为 npm / crates.io / GitHub / Thoughtworks Radar，许可以各包 license 为准（未逐一实拉，标「待核」项）。

## 逐项评估

### W72-01 satellite.js + N2YO MCP（卫星跟踪 JS 栈）
- **定位**：SGP4/SDP4 轨道预报 JS 库 + N2YO 实时星历/过境 MCP。
- **对照**：Look4Sat/satpy 卫星垂直已立项。
- **借鉴点**：①SGP4 轨道预报库可作 Look4Sat 的后端算法参考；②N2YO MCP 的「星历/过境」tool 目录；③JS 栈可复用前端可视化。
- **许可**：npm（待核，多数 MIT/Apache）。
- **落点**：docs/satellite-js-n2yo-评估.md

### W72-02 mcp-proxy（MCP 传输代理）
- **定位**：把 stdio 传输的 MCP 服务器桥接成 SSE/远程。
- **对照**：mcpserver 工具链 + MCP 客户端管理面（W65-05）。
- **借鉴点**：①stdio→SSE 桥接可复用为远程 MCP 接入；②传输层抽象；③代理级鉴权/多租户。
- **许可**：npm（待核）。

### W72-03 lora-packet + RF 频谱分析（JS 无线电工具）
- **定位**：LoRa PHYPayload 解码 JS 库 + RF 频谱 FFT/瀑布图 Web 库。
- **对照**：rf_brain + lora 工具链。
- **借鉴点**：①LoRa 载荷解析算法（对照 tools/lora_frame.py）；②Web 频谱瀑布图可视化；③浏览器端 SDR 前端。
- **许可**：npm（待核）。

### W72-04 pmcp + adk-agent（Rust MCP/Agent 栈）
- **定位**：Rust 原生 MCP SDK + Rust Agent 开发框架。
- **对照**：mcpserver（Python）+ 工具链。
- **借鉴点**：①Rust MCP SDK 的类型安全 tool 定义；②ADK 的 Agent 框架分层；③嵌入式侧 MCP 用 Rust 的可行性。
- **许可**：crates（待核）。

### W72-05 cortex-memory-core + agdb（Rust 记忆/图库）
- **定位**：Rust 图记忆引擎（decay+混合检索）+ Rust 嵌入式图数据库（Cypher）。
- **对照**：memory_maas + summer_memory 五元组 + neo4j 图记忆（W68-06）。
- **借鉴点**：①decay（记忆衰减）+ 混合检索；②嵌入式图库（无 Neo4j 重依赖）；③Cypher 风格查询。
- **许可**：crates（待核）。

### W72-06 desperado + peat-mesh（Rust SDR/mesh）
- **定位**：统一 SDR I/Q 数据流抽象（stdin/file/TCP/设备）+ Rust mesh（CRDT 同步）。
- **对照**：rf_brain SDR 链 + LoRaCanary mesh。
- **借鉴点**：①I/Q 数据流统一抽象；②CRDT mesh 同步；③Rust 实时 DSP。
- **许可**：crates（待核）。

### W72-07 Graphiti 时序知识图谱（Agent 持久记忆）
- **定位**：Bi-temporal 持久记忆——旧事实失效而非覆盖，sub-second 检索，MCP 原生集成。
- **对照**：memory_maas + 五元组（呼应 W73-03 cognee 图记忆）。
- **借鉴点**：①bi-temporal（事实失效而非覆盖）语义；②sub-second 图检索；③MCP 原生集成。
- **许可**：GitHub getzep/graphiti（Apache-2.0，可借鉴）。
- **落点**：docs/graphiti-时序记忆-评估.md

### W72-08 Feedback Sensors × skill_gate（Agent 质量门）
- **定位**：编译器/linter/测试套件等确定性质量门接入 Agent 产出管道，失败自动自纠正。
- **对照**：skill_gate（tools/skill_gate.py，已有）。
- **借鉴点**：①确定性质量门（编译器/linter/测试）接入产出；②失败自动自纠正闭环；③与 skill_gate 合并升级。
- **许可**：Thoughtworks Radar（方法论，参考设计）。

### W72-09 Sandboxed Execution（Agent 沙箱化）
- **定位**：隔离环境（microVM/container）运行 Agent，限制文件系统/网络/资源。
- **对照**：SPEC-R3 Sandboxed Execution + 权限内核（W73-08）。
- **借鉴点**：①microVM/container 隔离；②文件/网络/资源限制；③与权限内核协同。
- **许可**：Thoughtworks Radar（方法论）。

### W72-10 SLM 小模型路由 + 语义熵（降本）
- **定位**：小模型（Phi-4-mini/Qwen3-0.6B）路由替代大模型 + 语义熵幻觉检测。
- **对照**：K40 端上推理 + 熵引导蒸馏（W73-09）。
- **借鉴点**：①SLM 路由降本；②语义熵幻觉检测；③端上小模型部署。
- **许可**：Thoughtworks Radar（方法论）。

## 执行清单

- **完成**：10/10 逐项评估。
- **许可**：npm/crates 各包待核（未逐一实拉 license）；Graphiti 为 Apache-2.0。
- **原型**：W72-08 标「评估+原型」——质量门原型已在 skill_gate 方向（见 agent-74 权限内核），本卷只出评估。
