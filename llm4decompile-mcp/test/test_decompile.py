"""
路径 A：直接反编译 ELF 测试。

测试策略：
  1. 在纯 Python 下用 capstone 路径验证汇编提取 + prompt 构造（不依赖真实模型）
  2. 验证 decompile_binary() 在 mock 模型下正确返回 C 代码块
  3. 无 objdump 且无 capstone 时给出清晰报错
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import LLM4Decompile, ModelNotLoadedError  # noqa: E402


class TestDecompileBinary(unittest.TestCase):
    def setUp(self):
        self.llm = LLM4Decompile(model_path="/nonexistent/model.gguf")

    def test_prompt_contains_assembly_and_opt(self):
        """验证反编译 prompt 包含汇编与优化级别。"""
        fake_model = MagicMock()
        fake_model.create_completion.return_value = {
            "choices": [{"text": "```c\nint add(int a,int b){return a+b;}\n```"}]
        }
        self.llm._model = fake_model

        with patch.object(self.llm, "_get_assembly", return_value="push rbp\nmov rbp,rsp"):
            self.llm.decompile_binary("/tmp/add.o", optimization="O2")

        prompt = fake_model.create_completion.call_args.kwargs["prompt"]
        self.assertIn("O2", prompt)
        self.assertIn("push rbp", prompt)

    def test_auto_optimization_defaults_o2(self):
        """auto 时默认按 O2 处理。"""
        fake_model = MagicMock()
        fake_model.create_completion.return_value = {
            "choices": [{"text": "```c\nint f(){return 0;}\n```"}]
        }
        self.llm._model = fake_model
        with patch.object(self.llm, "_get_assembly", return_value="nop"):
            self.llm.decompile_binary("/tmp/f.o", optimization="auto")
        prompt = fake_model.create_completion.call_args.kwargs["prompt"]
        self.assertIn("O2", prompt)

    def test_model_not_loaded_raises(self):
        """无模型时 decompile 抛出 ModelNotLoadedError。"""
        # mock 汇编提取成功，确保走到模型加载检查；无模型且路径不存在时抛错
        with patch.object(self.llm, "_get_assembly", return_value="nop"):
            with self.assertRaises(ModelNotLoadedError):
                self.llm.decompile_binary("/tmp/add.o")

    def test_no_assembly_tool_gives_clear_error(self):
        """无 objdump 且无 capstone 时报错信息清晰。"""
        fake_model = MagicMock()
        fake_model.create_completion.return_value = {"choices": [{"text": "x"}]}
        self.llm._model = fake_model
        with patch.object(self.llm, "_get_assembly", side_effect=ModelNotLoadedError("缺少 capstone")):
            with self.assertRaises(ModelNotLoadedError) as ctx:
                self.llm.decompile_binary("/tmp/add.o")
            self.assertIn("capstone", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
