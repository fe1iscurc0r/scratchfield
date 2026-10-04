"""W121：Code Workspace —— Lumo 的代码编写/执行/测试工作区（沙箱受限）。

模块划分：
- `sandbox.py`：路径隔离 + 进程限制 + 命令白名单 + 审计（安全边界，W121-04）
- `tools.py`：六个工具（code_exec / file_read / file_write / file_edit / shell_exec / test_run，W121-01）
"""
