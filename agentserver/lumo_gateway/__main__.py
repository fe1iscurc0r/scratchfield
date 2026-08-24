"""python -m agentserver.lumo_gateway 入口。"""

from __future__ import annotations

import asyncio

from .main import main, setup_logging

if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
