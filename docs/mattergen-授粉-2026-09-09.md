# mattergen 无机材料生成模型授粉（W102-02）

> 2026-09-09 · 评估（不写实现）· 上游：microsoft/mattergen（1,816★，MIT，Python，微软官方无机材料生成模型，2026-08-27 活跃）
> 许可：MIT（授粉报告已复核）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/mattergen——以下引用为实读行号。

## 一、架构拆解（实读）

- 生成器：`CrystalGenerator`（src/mattergen/generator.py:185），`generate` 入口（generator.py:356）
  ——组成/性质条件 → 晶体结构生成。
- 去噪模型：`GemNetTDenoiser(ScoreModel)`（src/mattergen/denoiser.py:170）——GemNet-T 扩散评分网络。
- 条件化：`ModelTarget` 枚举（src/mattergen/diffusion/model_target.py:8）+ property_embeddings.py（性质嵌入）。
- 权重：checkpoints/ 目录随仓分发（体积见落地评估）。

## 二、授粉三大件①：源→目标映射

| 源组件（mattergen） | 目标模块 | 授粉方式 | 收益 |
|--------------------|---------|---------|------|
| 晶体生成管线 | 材料科研知识库（晶体结构数据管线） | 知识库结构参考 | 晶体数据管线设计 |
| 组成→结构→性质三阶段 | 材料科研模块 | 管线抽象参考 | 生成侧候选 |
| 晶体表示 | 知识库 schema | 数据结构参考 | 晶体条目 schema |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **CrystalGenerator 条件化生成**（generator.py:185/356）：组成+性质条件 → 结构——材料知识库
   「按组成查结构」的生成侧补全锚点。
2. **GemNetTDenoiser 评分网络**（denoiser.py:170）：扩散评分模型与晶体图的结合形态。
3. **ModelTarget 多目标条件枚举**（diffusion/model_target.py:8）+ property_embeddings 性质嵌入：
   生成条件化的数据结构参考。

## 四、落地评估（依赖/体积核实）

- 权重体积：checkpoints/ 需核实（授粉报告未给数，标注待核）。
- 推理依赖：torch + GPU 建议；CPU 推理慢。
- 结论：**暂缓（仅参考）**——生成侧候选与本地「表征/知识库」主线距离远；
  待材料线进入「新晶体筛选」阶段再启用。

## 五、许可裁定与结论

MIT 可借鉴；结论：**暂缓（仅参考）**，先收 schema 与三阶段管线抽象。

---
*评估：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill）*
