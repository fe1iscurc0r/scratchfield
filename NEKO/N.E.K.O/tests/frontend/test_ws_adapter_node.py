"""Run the page-side WebSocket adapter harness (WO-278 §2).

The harness (``ws-adapter.test.js``) loads the real
``static/app/ws-adapter.js`` with a fake ``window`` + fake bridge handle and asserts
the two semantics the page depends on:

1. ``sock.readyState`` is a **live** value (a bridged snapshot would break 32 call sites)
2. ``sock.onopen = fn`` assignment works (contextBridge cannot carry assignment semantics)

It needs node but not a browser, so it runs in the plain frontend lane.
"""
import json
import shutil
from pathlib import Path

import pytest

from tests.node_harness import run_node_script


@pytest.mark.frontend
def test_ws_adapter_semantics():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not found")
    root = Path(__file__).resolve().parents[2]
    source = Path(__file__).with_name("ws-adapter.test.js")
    result = run_node_script(
        node, f"require({json.dumps(str(source))});", cwd=root,
        capture_output=True, text=True, check=False, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "ws-adapter tests passed" in output, output
