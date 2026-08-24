# 授粉插件商城

所有授粉改造过的组件在这里登记。商城机制：**自由添加**。

## 添加一个插件（三步）

1. 把改造产物放进本仓（或指向已有路径）
2. 运行 `./scripts/plugin-add.sh <id> <name> <upstream> <license> <type> <path> [doc]`
3. 提交

## 安装到运行时

`./scripts/plugin-install.sh <plugin-id>`

按 type 处理：

| type | 处理 |
|------|------|
| `mcp` | 检查 mcpserver 注册（unified_call 自动发现） |
| `skill` | 拷贝到 `~/.hermes/skills/` |
| `coupled` | 已是本仓目录，无需安装 |
| `report` | 纯文档（授粉报告），仅打印路径 |

## 条目字段

| 字段 | 说明 |
|------|------|
| `id` | 唯一标识 |
| `name` | 展示名 |
| `upstream` | 上游仓库（`owner/repo`） |
| `license` | 上游许可（以 LICENSE 文件为准，SPDX id） |
| `type` | mcp / skill / coupled / report |
| `path` | 本仓内的代码落点 |
| `doc` | 授粉报告路径（可选） |
