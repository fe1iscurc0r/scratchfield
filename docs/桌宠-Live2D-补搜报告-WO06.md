# WO-06: 桌宠/Live2D 低星补搜报告

> 日期：2026-08-22 晚 | 委托：沈遥自做 | 状态：✅ 完成
> 模式：Discovery-Only（低星更软），4 路查询，铁条件过滤（非空许可/未归档）

## 查询与结果

| 查询 | 原始命中 | 过滤后 |
|------|---------|--------|
| live2d desktop pet (1..300★) | 30 | ~8 |
| vtuber live2d avatar (1..300★) | 30 | ~8 |
| desktop ai companion (1..300★) | 30 | ~8 |
| ai companion memory personality (1..300★) | 30 | ~8 |
| 合计去重 | 44 | **32** |

## 推荐候选（≤10 项，含最小实现标记）

| 项目 | ⭐ | 许可 | 体积 | NEKO 耦合潜力 |
|------|-----|------|------|--------------|
| **x380kkm/Live2DPet** | 80 | MIT | **5MB** 🟢 | Live2D 桌宠最小实现，直接参考渲染壳 |
| **Johnixr/peeky** | 29 | MIT | **0.5MB** 🟢🟢 | 超小，适合嵌入式/低配场景 |
| **watochidayo/ai-overlay** | 7 | MIT | **0.5MB** 🟢🟢 | AI overlay 悬浮层，MCP 工具显示 |
| **112Alan/sky-companion** | 10 | MIT | **2MB** 🟢 | 天空陪伴桌宠，轻量 |
| mini-yifan/CoView | 21 | MIT | 11MB | 多视角桌面小部件 |
| qiyueblues-design/zhuomianling | 17 | MIT | 13MB | ⚠️ 已有授粉报告（docs/zhuomianling-授粉报告.md），已处理 |
| euvictorldev/hades-agent | 47 | MIT | 37MB | Agent 桌面壳，参考价值 |
| FanyinLiu/Nexus | 16 | MIT | 52MB | 略重 |

## 排除项

- momori777/Artemis（281★ NOASSERTION 393MB）— 许可未明 + 巨大
- HappyFox001/Noema（129★ AGPL 46MB）— AGPL 可入但重
- MABIN/-cc-smart-companion（5★ 217MB）— 过大
- 其余 NOASSERTION 项 — 许可未核，暂缓

## 结论

1. **桌宠方向本轮补搜成功**：之前 0 命中，现在有 4 个 <10MB 最小实现（Live2DPet/peeky/ai-overlay/sky-companion）
2. **NEKO 壳候选**：Live2DPet（5MB）是渲染壳最优参考，peeky（0.5MB）是极致轻量参考
3. zhuomianling 已授粉（8-17），无需重复

## 后续建议

- 若要 NEKO 桌面壳：授粉勘察 Live2DPet（80★ MIT 5MB），提取 Live2D 渲染 + 桌宠交互逻辑
- 若要 MCP overlay：ai-overlay（0.5MB）可作为悬浮显示层参考
- 低星项目活跃度需单独确认（pushed_at 未逐个查，批量核实时补）

---
*存档：/tmp/wo06_final.json（32 项全量）*
