"""mcpserver/tests 的 pytest 配置：注册 robustness 标记。"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "robustness: 鲁棒性回归测试（可单独跑，不进常规 CI 高频路径）",
    )
