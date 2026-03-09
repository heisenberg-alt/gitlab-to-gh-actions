"""Entry point: python -m mcp_server"""

import asyncio
from mcp_server.server import main

if __name__ == "__main__":
    asyncio.run(main())
