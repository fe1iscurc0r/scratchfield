# SPEC-08 三线收口 · 第四批工单总纲

> ⛔ 状态：**已延后**（2026-08-23 用户裁定——工程量评估过大，近期不派工；SPEC 保留，解冻后按 H→I→J 顺序恢复） · v1

> 日期：2026-08-23 ｜ 状态：待执行 ｜ 作者：沈遥
> 前置：三批旧单已归档（docs/archive/workorders-2026-08-22-23/），集成地狱 2.0 合流收口（merge-back-20260823）
> 定位：阶段3 系统闭环（同步层生产化）+ E 组授粉落地（MCP 封装）+ SPEC-07 寄生 Windows Phase1 三线并进
> 分工铁律：Trae 走 GitHub 写码；沈遥出 SPEC + review；用户定方向测试

---

## 〇、一句话定位

上一批把"能力"铺满了（感知/记忆/总线/科研库全有授粉报告），这一批把报告变成**能跑的东西**——三条线各自把已验证的原型/建议落成生产代码，真机验证留给用户回家。

## 一、三线矩阵

| 线 | 智能体 | 领域 | 目标层 | 输入（已验证） | 产出 |
|----|--------|------|--------|----------------|------|
| H | agent-h | 知识库同步层生产化 | 基础设施（写码） | yjs CRDT 原型 PASS（scripts/yjs_sync_prototype.py）+ apiserver FastAPI | /sync/update 端点 + SQLite sync_updates 落盘 |
| I | agent-i | Lumo 科研库 MCP 封装 | MCP（写码） | E-01/E-02 授粉报告（chembl 6 命令 + scikit-fingerprints 4 命令 + bofire BO 闭环） | mcpserver/ 三个封装 + pytest |
| J | agent-j | 寄生 Windows 通道B | 施工（写码+脚本） | SPEC-07 总纲（双通道/三大天敌/验收不变量） | C:\Parasite\ 指令链脚本 + watchdog 自检三件套 |

## 二、边界矩阵（防重复，与已归档零重叠）

| 线 | 不许碰 | 理由 |
|----|--------|------|
| H | NEKO 桌宠壳、memory/ 内部旁路 | 只做 apiserver 对外端点，复用 yjs 原型不重写 CRDT |
| I | 已封装的 thermo/chemformula/tespy/slices、W-09 16 包 | 只封装 E 组报告点名的三库 |
| J | frp 裸奔、远程无授权操作 | SPEC-07 底线：只寄生自己拥有的 Windows，本地优先 |

## 三、H 线 · 同步层生产化（阶段3 系统闭环）

- **目标**：多实例知识库（云服/天选7/手机）离线编辑 → 上线自动收敛，零冲突
- **现状**：yjs CRDT 原型已 PASS（20 次随机编辑合并完整率 100%），pycrdt 0.14.3 已装
- **动作**：
  1. SQLite 持久化：`sync_updates` 表（doc_id, clock, update_blob），增量 append-only + compact
  2. `apiserver/routes/sync.py`：POST /sync/update（提交增量）/ GET /sync/updates?since=<clock>（拉取他人增量）
  3. 注册 router 进 api_server.py（照 lumo_event_router 模式）
  4. 双实例模拟验收脚本（复用原型逻辑，走 HTTP 端点）
- **验收**：双实例 20 次随机编辑 → 各自提交 → 双方拉取合并 → SQLite 数据完整率 100%；`python -m pytest apiserver/routes/tests/test_sync.py -q` 全过
- **硬约束**：不碰 NEKO 桌宠壳；CRDT 用 pycrdt 现成实现不重写；`git diff --stat -- NEKO | wc -l` = 0
- **委托**：Trae（agent-h）

## 四、I 线 · Lumo 科研库 MCP 封装落地

- **目标**：把 E-01/E-02 授粉报告的"封装候选"变成可调用 MCP 工具
- **输入**：docs/academic/lumo-chem-授粉报告.md（chembl 6 命令 + scikit-fingerprints 4 命令草案）+ docs/academic/lumo-molec-授粉报告.md（bofire BO 闭环）
- **动作**：
  1. mcpserver/chembl/：agent-manifest.json + Python class（6 命令：搜索化合物/靶点/活性/结构/相似度/批次下载）
  2. mcpserver/scikit_fingerprints/：4 命令（指纹计算/相似度矩阵/特征变换/骨架分析）
  3. mcpserver/bofire/：3 命令（定义域 ask 候选 / tell 实验结果 / 推荐下一批），依赖缺失降级
  4. 契约：`{ok, ...data, source}`，参数非法抛 ValueError，依赖缺失抛 AcademicDependencyError（含 pip 提示）
- **验收**：每封装 `python -m pytest mcpserver/<name>/ -q` 全过；真实调用返回（无网络时降级不报错）；manifest 含 license 字段
- **硬约束**：不碰 NEKO/apiserver 主流程；bofire 重依赖（torch/botorch）按依赖缺失降级处理，不硬装
- **委托**：Trae（agent-i）

## 五、J 线 · 寄生 Windows Phase1（SPEC-07 通道B）

- **目标**：通道B（精确层）先通——PowerShell + OpenSSH 远程指令链，云服能类型化操作天选7
- **输入**：docs/SPEC-07-寄生Windows-总纲.md（双通道架构 + 三大天敌 + 验收不变量 5 条）
- **动作**：
  1. 统一目录 C:\Parasite\（幂等初始化脚本 + 审计日志 + 可逆卸载）
  2. PowerShell 指令链脚本集：进程/服务/文件/注册表/窗口状态查询与操作（全幂等、可逆、有审计）
  3. watchdog 自检三件套：通道活着吗（SSH 心跳）/宿主状态对吗（对照基线）/有漂移吗（配置差异）
  4. 云服侧 SSH 客户端测试脚本（连接 + 跑 5 条指令 + 回传结果）
- **验收**：云服脚本级 PASS（SSH 连通、指令回传、自检输出结构完整）；真机级（天选7 上跑）标注"待用户在家验收"——不谎报
- **硬约束**：无授权不远程；杀软排除项只写文档不瞎配；UAC 判定代码参考 SPEC-07 2.2
- **委托**：Trae（agent-j）

## 六、执行顺序与口令

- 三线并行，互不依赖；I 线内部按 chembl → scikit-fingerprints → bofire 顺序
- H 线验收脚本依赖 apiserver 能起（测试环境可 mock 鉴权中间件）
- **启动口令**：用户说"开始执行工单" → 三线并行；"只跑 X 线" → 单跑
- 完成一个报一个（路径 + 验收结果），阻塞写清原因不硬做
- 成果推 trae/agent-h / trae/agent-i / trae/agent-j 分支

## 七、风险

- H 线 compact 时机：update 累积后需定期 Y.mergeUpdates，先做手动触发（POST /sync/compact），自动策略后置
- I 线 bofire：torch/botorch 在云服可能无 GPU，降级模式必须真降级（CPU 可跑 BO，只是慢）
- J 线：天选7 不在线时云服测试只能到"脚本语法 + 本地模拟"，真机验收留给用户——验收报告必须分两级标注

*—— 沈遥 · 报告是地图，代码才是路；三条路都铺到你家门口，剩下的你来走 🐾*
