"""Root entrypoint to execute the bot directly with `python run.py`."""

import asyncio
from src.main import main

if __name__ == "__main__":
    asyncio.run(main())
