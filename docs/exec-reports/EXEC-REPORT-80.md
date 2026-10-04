# EXEC-REPORT-80 · 第三十四期卷80（rsba1core 落地 + 图传授粉批）执行清单

**分支**：trae/agent-80 · **执行**：fe1iscurc0r · **日期**：2026-09-08

## 完成

- [x] W79-01 rsba1-core 纳入 vendor + 铁锚集成测试（`feat(w79-01)`）
  - clone fe1iscurc0r/rsba1-core → `vendor/rsba1-core`（保持 src 布局，不动上游源码；已移除嵌套 .git，按普通文件跟踪）
  - 懒加载链验证：`Rsba1Ic705Bridge` 导入不炸 / `_import_rsba1("rsba1.radio_link")` /
    `civ_commands.assert_allowed_freq` 可达
  - adapter.ensure() 补无包快速失败（「无法定位 rsba1 包」根因提示，不再伪装成连接失败）
  - `tests/test_rsba1_adapter.py`：8 测试（mock RadioLink 六工具 / RemoteUty 兜底 /
    双路失败人类可读 / 白名单越界 100·1000MHz / 无包降级）
- [x] W79-02 rf_brain Phase7 ↔ rsba1_adapter 联动契约（`feat(w79-02)`）
  - `mcpserver/rf_brain/test_phase7_rsba1_link.py`：10 测试
    （白名单同闸门契约 / ic705_set_freq 越界同闸门 / device_index 透传 pa.open /
    wavfile 校验失败关句柄 / wave.Error→RuntimeError / sim duration_s·max_samples 截断）
  - 真机对接点已标注于 IC705_INPUT_README（无需改动）
- [x] W79-03~08 六个勘察/评估报告落 docs/（每项分 commit）
  - wfbng-openhd-图传-评估 / px4-offboard-评估 / kg-中文RE-评估 /
    qopenhd-livevideo-地面端-评估 / ezwfb-rtl8812au-图传-评估 / ddpg-airsim-避障-评估
  - GPL-3.0 只参考设计；**GPL-2.0-only（EZ-WifiBroadcast/rtl8812au）标注法律硬冲突，只作架构参考**

## 回归

- 全量回归（tests/ + mcpserver/rf_brain/）：**1110 passed, 1 skipped**
- 注：`test_stream_chat_returns_visible_error_after_empty_stream_retries` 在缺
  gitignored `config.json` 的干净 worktree 中失败（attempts=0，环境依赖），补入
  最小 config.json 后通过——经主树对照确认为**环境既有问题**，非本卷改动引入。

## 合并

- [ ] 待用户收口：trae/agent-80 → main（本卷新增 vendor 源码 + 2 测试文件 + 6 报告 + adapter 小改）

## 阻塞 / 遗留

- [ ] vendor 纳入与「RSBA1_SRC_PATH 环境变量」二选一策略未在 README 注明
      （当前默认 vendor 路径；如需改环境变量方案需同步 README）
- [ ] 真机对接（IC-705 实物）留用户实测
