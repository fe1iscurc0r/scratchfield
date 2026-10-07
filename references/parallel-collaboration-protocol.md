# 陆墨多智能体并行协作协议 v2.0

**版本**：2026-07-30  
**核心原则**：文件隔离 · 任务并行 · 结果汇检 · 零等待

---

## 一、协作模式对比

### v1.0（旧）：串行流水线
```
任务 → 沈遥(架构) → 铁锚(审查) → 杜赞(决策) → 主代理(编码) → 推送
       ↑ 每步等待上一步完成，算力闲置率 ~60%
```

### v2.0（新）：并行流水线
```
                    ┌─ 沈遥(A组: 后端/Bridge/API) ─┐
任务 → 主代理分发 →  ├─ 铁锚(B组: 前端/审查/安全) ─┤ → 主代理汇检 → 推送
                    └─ 杜赞(C组: 验证/测试/架构) ──┘
                    ↑ 三组同时进行，各管独立文件，零冲突
```

---

## 二、角色-文件隔离矩阵

### A 组：沈遥（deepseek-v4-pro）→ 后端/Bridge/API

| 文件领域 | 具体文件 | 权限 |
|---|---|---|
| MCP 桥接层 | `mcpserver/material_science/matchat_bridge.py` | 读写 |
| MCP 工具层 | `mcpserver/material_science/matchat_tools.py` | 读写 |
| MCP Agent | `mcpserver/material_science/materialscience_agent.py` | 读写 |
| Agent 清单 | `mcpserver/material_science/agent-manifest.json` | 读写 |
| RAG 路由 | `apiserver/routes/rag.py` | 读写 |
| RAG 服务 | `rag/rag_service.py` | 读（仅验证） |
| RAG 存储 | `rag/vecdb_client.py` | 读（仅验证） |

**职责**：Matchat Bridge 维护、RAG 后端接口调试、MCP 工具注册、Playwright 自动化

### B 组：铁锚（千文 3.7plus）→ 前端/审查/安全

| 文件领域 | 具体文件 | 权限 |
|---|---|---|
| 前端视图 | `frontend/src/views/*.vue` | 读写 |
| 前端 API | `frontend/src/api/*.ts` | 读写 |
| Electron 主进程 | `frontend/electron/main.ts` | 读（仅审查） |
| Electron 模块 | `frontend/electron/modules/matchat.ts` | 读写 |
| Electron 预加载 | `frontend/electron/preload.ts` | 读写 |
| Electron 类型 | `frontend/src/electron.d.ts` | 读写 |
| 前端入口 | `frontend/src/main.ts` | 读（仅审查） |
| 论坛 API | `frontend/src/forum/api.ts` | 读写 |

**职责**：前端 TS 错误修复、Vue 组件审查、Electron 模块开发、安全漏洞审查

### C 组：杜赞（kimi 2.7code）→ 验证/测试/架构

| 文件领域 | 具体文件 | 权限 |
|---|---|---|
| 配置 | `config.json` | 读（不写，避免泄露） |
| 主程序 | `main.py` | 读+运行验证 |
| 系统配置 | `system/config.py` | 读 |
| 模型测试 | `test_rag_backend.py`, `test_matchat_v2.py` | 写测试 |
| 报告 | `reports/*.md` | 写 |

**职责**：架构决策验证、端到端测试、性能评估、方案拍板、报告撰写

### 主代理：协调+汇检+编码

| 职责 | 说明 |
|---|---|
| 任务分发 | 将需求拆解到 A/B/C 三组，明确输入输出 |
| 结果汇检 | 收集三组产物，检查一致性和完整性 |
| Git 操作 | 统一 add/commit/push，避免冲突 |
| 跨组协调 | 处理 A/B/C 组之间的依赖和冲突 |

---

## 三、并行执行规则

### 3.1 分派规则
1. **按文件域分派**：每个任务必须明确归属到 A/B/C 中的一个文件域
2. **零重叠**：同一文件在同一时刻只允许一个角色操作
3. **后台进程并行**：耗时操作（编译、浏览器测试、pip install）必须用后台任务

### 3.2 通信机制
```
主代理 → [任务分派] → A/B/C 三组并行
A/B/C  → [产出结果] → 主代理汇总
主代理 → [冲突检查] → Git 操作 → 推送
```

**关键**：主代理是唯一的 Git 操作者，A/B/C 不直接操作 Git

### 3.3 结果汇检检查点
1. **代码一致性**：检查不同组修改的代码是否语义冲突
2. **接口契约**：检查 A 组后端 API 与 B 组前端调用是否匹配
3. **安全审查**：铁锚的安全审查报告必须在推送前完成
4. **集成验证**：杜赞的 e2e 测试必须通过

---

## 四、当前项目文件归属图

```
scratchpad/
├── mcpserver/material_science/    ──→ 沈遥 (A组)
│   ├── matchat_bridge.py              桥接层/自动化
│   ├── matchat_tools.py               工具注册
│   ├── materialscience_agent.py       MCP Agent
│   └── agent-manifest.json            工具清单
├── frontend/                       ──→ 铁锚 (B组)
│   ├── src/views/KnowledgeView.vue    知识库视图
│   ├── src/views/*.vue                所有 Vue 组件
│   ├── src/forum/api.ts               论坛 API
│   ├── src/api/core.ts                核心 API
│   ├── electron/modules/matchat.ts   Matchat Electron 模块
│   ├── electron/main.ts               Electron 主进程
│   └── electron/preload.ts            预加载脚本
├── rag/                            ──→ 沈遥 (A组, 只读) + 杜赞 (C组, 验证)
│   ├── rag_service.py                 RAG 服务
│   └── vecdb_client.py                向量数据库客户端
├── apiserver/routes/               ──→ 沈遥 (A组)
│   └── rag.py                         RAG 路由
├── system/                         ──→ 杜赞 (C组)
│   └── config.py                      系统配置
├── reports/                        ──→ 杜赞 (C组)
│   └── *.md                           报告
├── config.json                     ──→ 只读 (所有人)
└── main.py                         ──→ 杜赞 (C组, 运行验证)
```

---

## 五、瓶颈缓解策略

### 5.1 通信瓶颈
- **零轮询**：A/B/C 组完成后直接标记完成，由主代理轮询收集（避免 A 等 B、B 等 C 的死锁）
- **批量传输**：每个角色的产出以「补丁包」形式一次性传递，而非逐行修改
- **缓存友好**：相同角色的文件合并修改，减少主代理的上下文切换

### 5.2 算力瓶颈
- **进程并行**：浏览器测试、编译、API 调用全部放入后台
- **模型复用**：同一角色在连续任务中复用模型上下文，避免重复加载
- **分批验证**：大任务拆分为「先跑通→再优化」两阶段，先用最小验证通过再完善

### 5.3 冲突瓶颈
- **文件锁**：每个角色在操作文件前声明独占权
- **时序检查**：主代理在汇检时做 git diff，检查是否有未协调的重叠修改
- **回滚保护**：每组修改前自动 git stash，出错可快速恢复

---

## 六、执行流程示例

### 本轮任务分派示例（按 v2.0）：

```
用户需求：修复前端 TS 错误 + 调试 Matchat Bridge + 验证 RAG

主代理分派：
├── A组(沈遥):  调试 matchat_bridge.py DOM 选择器 (独立文件)
├── B组(铁锚):  修复 KnowledgeView.vue / forum/api.ts / matchat.ts 的 TS 错误 (独立文件)  
└── C组(杜赞):  运行 test_rag_backend.py 验证 RAG 接口 (独立文件)

三组并行 → 主代理汇检 → 推送到 Gitee
```

**vs v1.0 串行**：沈遥修 bridge → 铁锚审查 → 杜赞验证 → 主代理编码，总耗时减少 50-70%
