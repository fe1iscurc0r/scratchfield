# JLC-EDA 专业版客户端 API 地图（3.2.175, pro-api 0.3.12）

> 来源：lceda-pro-linux-x64-3.2.175.zip 解包勘察（2026-08-22 实验田维护者）
> 位置：resources/app/assets/pro-api/0.3.12.50234059/api.js（1.9MB）
> 验证：Trae 实测确认 `eda.sys_FileManager.getDocumentSource()` 是文档读取入口

## 顶层模块（26 个 sys_*）

| 模块 | 用途 | HW-06 相关性 |
|------|------|-------------|
| **sys_FileManager** | 文档读写管理 | ⭐ getDocumentSource() 核心入口 |
| sys_FileSystem | 文件系统 | 工程文件落盘 |
| sys_FormatConversion | 格式转换 | 原理图→图片/其他格式 |
| sys_WebSocket | WebSocket 通道 | ⭐ 扩展桥接通道 |
| sys_MessageBus | 消息总线 | 事件订阅 |
| sys_Dialog / sys_MessageBox / sys_ToastMessage | 弹窗 | 交互反馈 |
| sys_Setting | 设置 | 扩展配置 |
| sys_Storage | 存储 | 本地缓存 |
| sys_ShortcutKey | 快捷键 | 模拟按键 |
| sys_HeaderMenu / sys_RightClickMenu / sys_PanelControl | UI 控制 | 屏幕通道辅助 |
| sys_Environment / sys_ClientUrl | 环境信息 | 版本/环境判断 |
| sys_Unit / sys_Math | 单位/数学 | 坐标换算 |
| sys_Log / sys_Timer / sys_Window / sys_IFrame / sys_I / sys_LoadingAndProgressBar / sys_FontManager / sys_Message / sys_Tool | 基础设施 | 一般 |

## 关键接口（api.js 实搜）

- `eda.sys_FileManager.getDocumentSource()` — **文档源码读取（Trae 实测）**
- `eda.sys_WebSocket.*` — WebSocket 桥
- 注意：`eda.editor.getDocument()` **不存在**（Trae 勘误，原 SPEC 写法已改）

## 用法

- 扩展通过 extension.json 声明权限，连接器插件调用 `eda.*` API
- 云服无头环境跑不了 GUI；API 调用需在有客户端的机器（天选7）上执行
- 配套脚本：Trae 已交付 easyeda_get_document.mjs（接线脚本，等真机）

## 后续

- HW-06 真机环：天选7 装 EasyEDA Pro → 跑 easyeda_get_document.mjs → getDocumentSource 取 JSON
- 寄生参数提取 Phase1：拿到文档 JSON 后 → 解析网络/元件 → 提取寄生
