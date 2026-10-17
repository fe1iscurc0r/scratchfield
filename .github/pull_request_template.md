## 描述

简要描述此 PR 的更改。

## 类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 文档更新
- [ ] 重构
- [ ] 其他

## 硬线校验（按改动路径二选一）

- [ ] 动了 `mcpserver/agent_open_launcher/**` 或 `frontend/electron/**` ⇒ **必须粘贴**
      `python scripts/verify-runtime-env-wiring.py --ci` 的完整输出（**5/5 PASS** 才算过）
- [ ] 未动上述路径 ⇒ 本项不适用

> 为什么放这儿：CI 的 `ENABLE_LINT` / `ENABLE_CI_TEST` 闸门在账户计费未解封前不会被调度，
> PR 阶段没有自动守卫 —— 这一条是当下**唯一生效**的门禁。
> 恢复流程见 `docs/ci-闸门恢复清单-2026-10-17.md`。

## 测试

- [ ] 已运行 `python -m ruff check .`
- [ ] 已运行 `npm run lint`（如涉及前端）
- [ ] 已运行相关测试 `python -m pytest tests/`
- [ ] 手动验证通过

## 审查

- [ ] 铁锚审查（代码质量）
- [ ] 沈遥审查（架构一致性）

## 关联 Issue

如有。
