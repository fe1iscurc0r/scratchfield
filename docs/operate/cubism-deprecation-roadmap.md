# Cubism 弃用路线图（Ayagami 灰度 → 全量）

> 工单 263 任务 C。**只出路线图，不动 NEKO 代码**（`git diff --stat -- NEKO` 应为 0）。

## 0. 现状实测（`grep -rln "cubism" NEKO/ --include=*.ts --include=*.js`）

共 **9** 个文件命中（2026-10-20 实测）：

| # | 文件 | 角色 |
|---|---|---|
| 1 | `NEKO/N.E.K.O/static/live2d/live2d-init.js` | **主渲染入口**（Cubism 初始化） |
| 2 | `NEKO/N.E.K.O/static/libs/index.min.js` | Cubism SDK 打包产物 |
| 3 | `NEKO/N.E.K.O/static/app/app-chat-avatar.js` | 聊天头像渲染 |
| 4 | `NEKO/N.E.K.O/static/app/app-interpage/bootstrap-resources-and-model-reload.js` | 模型热重载 |
| 5 | `NEKO/N.E.K.O/static/js/index.js` | 主 JS 入口 |
| 6 | `NEKO/N.E.K.O/static/js/card_maker_embed_bootstrap.js` | 角色卡嵌入 |
| 7 | `NEKO/N.E.K.O/static/touch-config.js` | 触摸交互参数 |
| 8 | `NEKO/N.E.K.O/static/vrm/vrm-init.js` | VRM 分支（与 Cubism 并存） |
| 9 | `NEKO/N.E.K.O/tests/unit/live2d_motion_curve.test.js` | 动作曲线单测 |

**结论**：渲染入口集中在 `static/live2d/live2d-init.js` + SDK 打包 `static/libs/index.min.js`；
其余文件是**消费方**（头像、热重载、触摸参数、测试）。换内核时前两个是必须改的，后者只需适配。

## 1. 三阶段

### 阶段 1 · 调研（能力盘点）

- 输入：Ayagami 的 API 面（加载/参数/物理/表情/遮罩/口型）。
- 产出：下方**差异矩阵**填满，缺失项逐条给出替代方案或"暂缺"结论。
- 出口条件：矩阵无空行，且每项缺失都有明确处置（自研 / 不做 / 等上游）。

### 阶段 2 · 灰度（单角色双渲染并行）

- 做法：选 1 个角色，同一份模型同时用 Cubism 与 Ayagami 渲染，**参数快照对比**。
- 判据：见 §3 回退条件。
- 出口条件：连续 **7 天**无回退条件命中，且主观观感差异被记录。

### 阶段 3 · 全量（默认切 Ayagami，Cubism 保留兼容）

- 做法：`live2d-init.js` 增加后端选择（默认 ayagami，回退 cubism）；
- 兼容：保留 Cubism SDK 至少一个大版本，给角色卡留迁移窗口；
- 出口条件：全部角色卡在 Ayagami 下通过，且 Cubism 回退路径仍可用。

## 2. 差异矩阵（≥8 行）

| 能力 | Cubism | Ayagami | 差距与处置 |
|---|---|---|---|
| 模型加载（moc3/model3.json） | 原生 | 需转换格式 | 转换器自研或等上游；**阶段 1 必答** |
| 参数控制（ParamAngleX 等） | 原生 | 支持（命名可能不同） | 需名称映射层 |
| 物理演算 | 原生 | 待核实 | 若无，暂由 JS 侧实现简易弹簧 |
| 表情叠加 | 原生 | 待核实 | 可退化为参数混合 |
| 遮罩/裁剪 | 原生 | 待核实 | 影响眼白/口腔；缺失则降级为整体渲染 |
| 音频口型（LipSync） | 原生 | 待核实 | 可先用音量驱动参数 |
| 动作曲线（motion3.json） | 原生 | 待核实 | 单测 `live2d_motion_curve.test.js` 需并行实现 |
| 渲染后端（WebGL/WebGPU） | WebGL | 待核实 | 若仅 WebGPU，则旧机器不可用 |
| 触摸命中区域 | 原生 | 需自算 | 复用 `touch-config.js` 的包围盒 |
| 包体大小 | SDK 较大 | 预计更小 | 收益项，不作硬化条件 |

> "待核实"必须由阶段 1 补齐；**不许**在没有实测的情况下写"支持"。

## 3. 回退条件（可判定）

灰度期命中**任一**条即退回 Cubism，并记录为阻塞项：

1. **表情参数偏差 > 5%**，连续 3 天（按参数快照的归一化差值算）；
2. 任一角色出现**渲染崩溃或黑屏**（日志有 error）；
3. **口型与音频不同步 > 200 ms**（取 10 次采样的中位数）；
4. 帧率较 Cubism 下降 **> 30%**（同机同模型对比）。

## 4. 工期与阻塞

| 阶段 | 预估 | 主要阻塞 |
|---|---|---|
| 调研 | 1–2 周 | Ayagami 的格式转换能力未知（矩阵第 1 行） |
| 灰度 | 2–3 周 | 需先完成转换器；单角色双渲染的对比工具 |
| 全量 | 2 周 | 角色卡迁移工作量取决于角色数量 |

**当前阻塞**：阶段 1 的第 1 项（moc3/model3.json 转换）没有结论前，不宜进入灰度。

## 5. 红线

- 本文件不包含任何 NEKO 代码改动；
- 切内核前必须保留 Cubism 回退路径；
- 不得把"待核实"写成"已支持"。

## 6. 命名与检索约定

- 本文正文用 `Cubism` 指产品名；**代码与配置里一律小写 `cubism`**（与 `live2d-init.js` 现有写法一致）。
- 后续所有检索请用：`grep -rn "cubism" NEKO/ --include=*.js`（大小写敏感时会漏掉，建议 `-i`）。
- 回退开关的键名定为 `renderer_backend`，取值 `cubism` / `ayagami`，默认 `ayagami`。
