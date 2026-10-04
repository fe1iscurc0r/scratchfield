"""workflow-board CLI 包装脚本（等价 `python -m mcpserver.workflow`）。

用法：python scripts/workflow_board.py <cmd> ...
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mcpserver.workflow.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
