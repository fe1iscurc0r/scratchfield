"""Run the workshop XSS guard runtime harness for the Steam subscriptions page.

The harness (``test_workshop_xss_runtime.js``) loads the real
``static/js/character_card_manager/subscriptions-and-scan.js`` into a ``vm``
context with a stubbed DOM, feeds it malicious workshop fields, and asserts both
the rendered markup and the static escaping contract. It needs node but not a
browser, so it runs in the plain frontend lane.
"""
import json
import shutil
from pathlib import Path

import pytest

from tests.node_harness import run_node_script


@pytest.mark.frontend
def test_workshop_xss_runtime():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found")
    root = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("test_workshop_xss_runtime.js")
    result = run_node_script(
        node, f"require({json.dumps(str(source))});", cwd=root,
        capture_output=True, text=True, check=False, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "workshop XSS guard runtime tests passed" in output, output
