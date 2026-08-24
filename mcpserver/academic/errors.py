"""academic 接口层公共错误与降级契约。"""
from __future__ import annotations


class AcademicDependencyError(RuntimeError):
    """运行依赖缺失（只标注不否决：装上即恢复，接口契约不变）。

    message 必须含 pip install 提示，供 Lumo/用户自助恢复。
    """

    def __init__(self, package: str, pip_name: str, extra: str = ""):
        self.package = package
        self.pip_name = pip_name
        hint = f"{package} 未安装：pip install {pip_name} 后可用"
        if extra:
            hint += f"（{extra}）"
        super().__init__(hint)


def require(package: str, pip_name: str, extra: str = ""):
    """惰性导入并返回模块；缺失抛 AcademicDependencyError（统一降级入口）。"""
    import importlib
    try:
        return importlib.import_module(package)
    except ImportError as e:
        raise AcademicDependencyError(package, pip_name, extra or str(e)) from e
