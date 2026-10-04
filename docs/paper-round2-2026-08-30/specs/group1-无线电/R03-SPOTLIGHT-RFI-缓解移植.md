# R03 SPOTLIGHT RFI 缓解移植

> 来源分组：group1-无线电

【SPEC】把 SPOTLIGHT 双极化 RFI 实时缓解思路（误检↓98%、S/N↑2.7×）移植 rf_brain 频谱后处理；验收=实现 rf_brain 滤波链 RFI 模块 + 合成干扰测试。
【工单】①读 G6-1 digest 的 SPOTLIGHT 要点②设计双通道 RFI 检测（极化域）③实现滤波链 butterworth/自适应陷波 ④合成干扰测试。
【提示词】你是 rf_brain DSP 开发 AI。实现 RFI 缓解模块：读 digest-g6-1-2026-08-30.md 的 SPOTLIGHT 授粉段，实现 rfi_mitigation.py：双通道能量比检测 RFI + 自适应陷波滤除。用合成信号（窄带干扰+弱信号）验证 S/N 提升。验收：pytest ≥4 用例；合成测试 S/N 提升 ≥1.5×；不碰 NEKO。
