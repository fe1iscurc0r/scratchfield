# SPEC-10 三线收口解冻 · 第六批工单总纲 · v1

> 日期：2026-08-23 ｜ 状态：**执行中**（H/I 两线解冻） ｜ 作者：沈遥
> 前置：SPEC-08（第四批三线收口）整体延后存档（docs/SPEC-08-三线收口-第四批工单-总纲.md）；用户裁定仅解冻 H、I 两线，J 线继续冻结
> 定位：SPEC-08 三线中工程量可控的两条先跑——知识库同步层生产化（H）+ Lumo 科研库 MCP 封装落地（I）
> 分工铁律：Trae 走 GitHub 写码；沈遥出 SPEC + review；用户定方向测试

---

## 〇、一句话定位

SPEC-08 原计划三线齐发，工程量评估过大后整体冻结。用户裁定：**H、I 两线解冻执行**（纯 Python + SQLite，云服可全量验收），**J 线（寄生 Windows）继续冻结**（依赖天选7 真机，用户未排期）。本批是"解冻批"——工单内容与 SPEC-08 §三/§四同源，但独立成纲、自包含，Trae 只需读本文件 + 各自提示词，不必翻 SPEC-08。

## 一、两线矩阵

| 线 | 智能体 | 领域 | 目标层 | 输入（已验证） | 产出 | 状态 |
|----|--------|------|--------|----------------|------|------|
| H | agent-h | 知识库同步层生产化 | 基础设施（写码） | yjs CRDT 原型 PASS（scripts/yjs_sync_prototype.py）+ apiserver FastAPI | /sync 端点 + SQLite sync_updates 落盘 | ✅ 解冻执行 |
| I | agent-i | Lumo 科研库 MCP 封装 | MCP（写码） | E-01/E-02 授粉报告（chembl 6 命令 + scikit-fingerprints 4 命令 + bofire BO 闭环） | mcpserver/ 三个封装 + pytest | ✅ 解冻执行 |
| J | agent-j | 寄生 Windows 通道B | 施工（写码+脚本） | SPEC-07 总纲 | C:\Parasite\ 脚本 | ⛔ 继续冻结（真机依赖，不派工） |

## 二、边界矩阵（防重复）

| 线 | 不许碰 | 理由 |
|----|--------|------|
| H | NEKO 桌宠壳、memory/ 内部旁路 | 只做 apiserver 对外端点，复用 yjs 原型不重写 CRDT |
| I | 已封装的 thermo/chemformula/tespy/slices、W-09 16 包 | 只封装 E 组报告点名的三库（chembl/scikit-fingerprints/bofire） |
| H↔I | 对方目录 | H 不碰 mcpserver/ 科研封装；I 不碰 apiserver/ 同步端点 |

## 三、H 线 · 同步层生产化（解冻自 SPEC-08 §三）

- **目标**：多实例知识库（云服/天选7/手机）离线编辑 → 上线自动收敛，零冲突
- **现状**：yjs CRDT 原型已 PASS（20 次随机编辑合并完整率 100%），pycrdt 0.14.3 已装
- **动作**：
  1. SQLite 持久化：`sync_updates` 表（doc_id, clock, update_blob），增量 append-only + 手动 compact（Y.mergeUpdates）
  2. `apiserver/routes/sync.py`：POST /sync/update（body: {doc_id, clock, update_b64}，upsert 增量）/ GET /sync/updates?doc_id=&since=<clock>（按 clock 排序拉增量）/ POST /sync/compact（触发 merge）
  3. 注册 router 进 api_server.py（照 apiserver/routes/lumo_event.py 的 include_router 模式；测试环境可 mock 鉴权中间件）
  4. `apiserver/routes/tests/test_sync.py`：双实例模拟 20 次随机编辑（写/改/删 45:35:20）→ 各自 POST 提交 → GET 拉取 → pycrdt 合并 → assert 双方视图一致且完整率 100%
- **验收**：
  - `python -m pytest apiserver/routes/tests/test_sync.py -q` 全过
  - 测试内含 assert 完整率 == 100%
  - `grep sync_updates apiserver/routes/sync.py` 非空（SQLite 表真实存在）
- **硬约束**：不碰 NEKO 桌宠壳（`git diff --stat -- NEKO | wc -l` = 0）；CRDT 用 pycrdt 现成实现禁止重写；同 key 并发写是 LWW（逻辑时钟），不引入自定义墙钟语义
- **委托**：Trae（agent-h，分支 trae/agent-h）

## 四、I 线 · Lumo 科研库 MCP 封装落地（解冻自 SPEC-08 §四）

- **目标**：把 E-01/E-02 授粉报告的"封装候选"变成可调用 MCP 工具
- **输入**：
  1. docs/academic/lumo-chem-授粉报告.md（chembl 6 命令 + scikit-fingerprints 4 命令草案）
  2. docs/academic/lumo-molec-授粉报告.md（bofire BO 闭环）
  3. docs/academic/MODEL_INTERFACE.md（接口格式参考）
- **通用契约**（三封装都遵守）：返回 `{ok: true, ...data, source: "<库名>"}`；参数非法抛 ValueError；依赖缺失抛 AcademicDependencyError（异常含 pip install 提示）；每封装含 agent-manifest.json（含 license 字段）+ Python class + 单元测试
- **动作**：
  1. `mcpserver/chembl/`：6 命令——搜索化合物 / 靶点信息 / 活性数据 / 结构获取 / 相似度搜索 / 批次下载（chembl_webresource_client，Apache-2.0）
  2. `mcpserver/scikit_fingerprints/`：4 命令——指纹计算 / 相似度矩阵 / 特征变换 / 骨架分析（scikit-fingerprints + RDKit，MIT；RDKit 缺失降级）
  3. `mcpserver/bofire/`：3 命令——define_domain / ask_candidates / tell_results（bofire，BSD-3-Clause；torch/botorch 缺失降级返回说明，不硬装）
- **验收**：
  - 每封装 `python -m pytest mcpserver/<name>/ -q` 全过
  - 真实调用返回数据（无网络/无依赖时降级返回不报错）
  - manifest 含 license 字段（chembl: Apache-2.0 / scikit_fingerprints: MIT / bofire: BSD-3-Clause）
- **硬约束**：不碰 NEKO/apiserver 主流程（`git diff --stat -- NEKO apiserver | wc -l` = 0）；bofire 重依赖按依赖缺失降级处理，不硬装
- **委托**：Trae（agent-i，分支 trae/agent-i）

## 五、执行顺序与口令

- 两线完全独立：独立分支、独立验收、互不依赖，可只跑一线
- I 线内部按 chembl → scikit-fingerprints → bofire 顺序（依赖从轻到重）
- **启动口令**：用户说"开始执行工单" → 两线并行；"只跑 H" / "只跑 I" → 单跑
- 完成一个报一个（路径 + 验收结果），阻塞写清原因不硬做
- 成果推 trae/agent-h / trae/agent-i 分支

## 六、风险

- H 线 compact 时机：update 累积后需定期 Y.mergeUpdates，先做手动触发（POST /sync/compact），自动策略后置
- H 线验收脚本依赖 apiserver 能起（测试环境可 mock 鉴权中间件）
- I 线 bofire：torch/botorch 在云服可能无 GPU，降级模式必须真降级（CPU 可跑 BO，只是慢）
- I 线网络：chembl 真实调用依赖外网，无网络时降级返回不报错

*—— 沈遥 · 报告是地图，代码才是路；两条先铺到你家门口，第三条等你的机器到家 🐾*
