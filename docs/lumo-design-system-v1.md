# Lumo 设计令牌（Design Tokens）v1

> 用途：lumo/scratchfield 品牌视觉身份的单一事实源。不依赖美工组——这是设计系统，不是插画。
> 原则：领域隐喻 = 材料科学（质谱、培养皿、烧杯、荧光）。深色科研风，克制，数据优先。
> 适用：前端 UI（frontend/src/style.css）、landing/README 视觉、公开仓徽章配色。

## 1. 品牌身份一句话

**Lumo 陆墨 = 材料学科研伴侣 + 融合系统门面。** 视觉语言是"实验台 + 质谱仪"，不是"聊天机器人"。

## 2. 色板（CSS Custom Properties）

```css
:root {
  /* 基底：深夜实验台 */
  --lumo-bg:        #0e1116;   /* 主背景：深蓝黑（替换 Naga 的 #110901 棕黑） */
  --lumo-bg-elev:   #161b22;   /* 卡片/面板 */
  --lumo-bg-inset:  #0a0d12;   /* 输入框/内嵌 */

  /* 主色：质谱蓝（身份色） */
  --lumo-primary:   #4f8cff;   /* 按钮/链接/焦点 */
  --lumo-primary-dim:#2d5bb5;  /* hover/按下 */
  --lumo-primary-tint: rgba(79, 140, 255, 0.12); /* 选中背景 */

  /* 辅色：培养皿绿（数据/成功） */
  --lumo-success:   #3fb950;
  /* 烧杯橙（警告） */
  --lumo-warning:   #d29922;
  /* 坩埚红（错误/危险） */
  --lumo-danger:    #f85149;

  /* 文本：质谱刻度灰阶 */
  --lumo-text:      #e6edf3;   /* 主文本 */
  --lumo-text-dim:  #9da7b3;   /* 次要文本 */
  --lumo-text-faint:#6e7681;   /* 占位/禁用 */

  /* 线条 */
  --lumo-border:    #2b3138;
  --lumo-border-strong: #3d444d;
}
```

色相理由：蓝 = 数据/质谱/冷静；绿 = 生长/培养/成功；橙红仅警示。避开 Naga 的暖棕黑，一眼不是套壳。

## 3. 字体

```css
--lumo-font-ui:   'Noto Sans SC', system-ui, sans-serif;   /* UI/正文 */
--lumo-font-display: 'Noto Serif SC', 'Noto Sans SC', serif; /* 标题/引言——衬线 = 学术 */
--lumo-font-mono: 'JetBrains Mono', 'Cascadia Code', monospace; /* 数据/代码 */
```

衬线标题是"学术感"的关键，与通用 AI 聊天产品的无衬线 UI 拉开。

## 4. 间距/圆角/阴影（8pt 网格）

```css
--lumo-space-1: 4px;   --lumo-space-2: 8px;   --lumo-space-3: 12px;
--lumo-space-4: 16px;  --lumo-space-5: 24px;  --lumo-space-6: 32px;
--lumo-radius-sm: 4px; --lumo-radius-md: 8px; --lumo-radius-lg: 12px;
--lumo-shadow-1: 0 1px 3px rgba(0,0,0,.4);
--lumo-shadow-2: 0 4px 12px rgba(0,0,0,.5);
```

## 5. 组件级 token（落地示例）

| 组件 | 取值 |
|---|---|
| 按钮主 | bg `--lumo-primary` / text `#fff` / radius md / padding 6px 16px |
| 卡片 | bg `--lumo-bg-elev` / border `--lumo-border` / radius lg / shadow-1 |
| 数据面板 | bg `--lumo-bg-inset` / mono 字体 / text-dim 标签 |
| 导航激活 | bg `--lumo-primary-tint` / 左 2px `--lumo-primary` 边 |
| 引言/格言 | serif display / text-dim / 左 border-primary |

## 6. 应用顺序（不碰运行中 UI）

1. 新页面/landing 直接用 token（`frontend/src/style.css` 的 `:root` 替换或追加）
2. README/公开仓徽章用主色 `#4f8cff` + 底色 `#0e1116`
3. 老页面渐进迁移（先导航/按钮/卡片，不整体重排）
4. `_design_source/pages/` 任务面板按 token 重绘时同步

## 7. 验收

- `grep -c "lumo-primary" frontend/src/style.css` ≥ 1（token 已进前端）
- README 徽章/头图用主色
- 新页面无 Naga 暖棕黑残留（`#110901` 不出现）

---

*制定：实验田维护者（Hermes）· 2026-08-25 · 依据：lumo 身份层改造（scratchfield README v2）*
