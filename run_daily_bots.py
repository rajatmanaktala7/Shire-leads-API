import asyncio
import json

from app.database import init_db
from app.services.lead_bot_service import run_daily_suite


async def main():
    init_db()
    result = await run_daily_suite()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
