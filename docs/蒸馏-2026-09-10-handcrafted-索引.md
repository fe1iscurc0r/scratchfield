# 蒸馏索引 · handcrafted-persona-engine（2026-09-10）

> 上游：elevenyellow/handcrafted-persona-engine（1363⭐，**无 LICENSE → 仅蒸馏不融合**，落地代码全部原创）

## 蒸馏文档（三份）

| 文档 | 内容 |
|------|------|
| docs/handcrafted-lipsync-rvc-distill-2026-09-10.md | 唇形同步（Part A：PhonemePose 九维/双目标插值/播放进度驱动）+ RVC（Part B） |
| docs/handcrafted-tts-engine-distill-2026-09-10.md | TTS 引擎 + 增量句子积累器 + CTC 对齐 |
| docs/handcrafted-system-skeleton-distill-2026-09-10.md | 资产管线（InstallManifest/AssetCatalog/双快照）+ ASR/LLM + 对话编排 |

## 本批工单授粉状态（AGENT_100 · trae/agent-100）

| 工单 | 状态 | 产出 |
|------|------|------|
| W100-01 唇形同步 | ✅ 完成 | tools/lumo/lip_sync/（拼音口型表 21声母+36韵母+SIL/停顿 + 双目标插值平滑器 + 播放进度驱动），9 测试全绿 |
| W100-02 TTS 增量句子积累器 | ✅ 完成 | tools/lumo/tts_pipeline.py（标点预检/末段保留/可插拔分句），8 测试全绿 |
| W100-03 资产管线 | ✅ 完成（轻落地+评估） | tools/lumo/asset_manifest.py（manifest+sha256+缺失检测），6 测试全绿 + 评估报告 |
| W100-04 RVC 选型 | ✅ 完成（评估） | docs/handcrafted-RVC选型评估-2026-09-10.md（选型 rvc-python，独立服务+manifest 联动） |

## 许可铁律回顾

上游无 LICENSE：本批全部代码按蒸馏文档设计思想**原创实现**，未复制上游源码；
各模块注释与报告均已标注「设计参考 handcrafted-persona-engine（无 LICENSE）」。

---
*索引：fe1iscurc0r · 2026-09-10*
