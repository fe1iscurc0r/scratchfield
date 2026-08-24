"""
路径 B：Ghidra 润色测试（核心路径，RS-BA1 PE 主用）。

测试策略：无模型时注入 mock LLM，验证：
  1. polish_ghidra_output() 正确构造 prompt 并提取 C 代码块
  2. 变量名/控制流润色由模型完成，本层保证 prompt 模板与后处理正确
  3. 无模型且模型路径不存在时抛出 ModelNotLoadedError
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inference import LLM4Decompile, ModelNotLoadedError  # noqa: E402

# 一个典型的 Ghidra 伪 C 输出（取自 SPEC 6.2）
GHIDRA_OUTPUT = """
undefined8 FUN_140012340(longlong param_1,uint param_2)
{
  longlong lVar1;
  undefined8 uVar2;

  lVar1 = *(longlong *)(param_1 + 0x10);
  if (lVar1 == 0) {
    uVar2 = 0xffffffff;
  }
  else {
    uVar2 = (**(code **)(lVar1 + 0x28))(param_2);
  }
  return uVar2;
}
"""


class TestPolishGhidra(unittest.TestCase):
    def setUp(self):
        self.llm = LLM4Decompile(model_path="/nonexistent/model.gguf")

    def test_prompt_contains_context_and_pseudo_c(self):
        """验证润色 prompt 包含函数名、上下文和原始伪 C。"""
        fake_model = MagicMock()
        fake_model.create_completion.return_value = {
            "choices": [{"text": "```c\nint result;\n```"}]
        }
        self.llm._model = fake_model

        self.llm.polish_ghidra_output(
            pseudo_c=GHIDRA_OUTPUT,
            function_name="send_ci_v_command",
            context_hint="Icom CI-V protocol: sends a command byte to radio",
        )

        prompt = fake_model.create_completion.call_args.kwargs["prompt"]
        self.assertIn("send_ci_v_command", prompt)
        self.assertIn("Icom CI-V protocol", prompt)
        self.assertIn("FUN_140012340", prompt)

    def test_strips_markdown_fence(self):
        """验证 markdown 代码块包裹被去除。"""
        fake_model = MagicMock()
        fake_model.create_completion.return_value = {
            "choices": [{"text": "```c\nint add(int a, int b) { return a + b; }\n```"}]
        }
        self.llm._model = fake_model

        result = self.llm.polish_ghidra_output(pseudo_c=GHIDRA_OUTPUT)
        self.assertIn("int add(int a, int b)", result)
        self.assertNotIn("```", result)

    def test_model_not_loaded_raises(self):
        """无模型且路径不存在时抛出 ModelNotLoadedError。"""
        with self.assertRaises(ModelNotLoadedError):
            self.llm.polish_ghidra_output(pseudo_c=GHIDRA_OUTPUT)

    def test_extract_c_code_no_fence(self):
        """后处理：无 fence 的纯文本直接返回。"""
        self.assertEqual(LLM4Decompile._extract_c_code("int x = 1;"), "int x = 1;")

    def test_get_status_not_loaded(self):
        """未加载模型时状态为 not_loaded。"""
        st = self.llm.get_status()
        self.assertFalse(st["model_loaded"])
        self.assertEqual(st["status"], "not_loaded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
