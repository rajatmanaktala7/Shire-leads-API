import asyncio
import json
import sys

from app.config import settings
from app.database import init_db
from app.services.lead_bot_service import run_daily_suite


async def main():
    # Cron should fail clearly for genuinely missing search configuration,
    # but numeric/blank env mistakes no longer crash app import.
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        print(json.dumps({
            "status": "SKIPPED",
            "reason": "No web-search provider configured",
            "version": settings.VERSION,
        }, indent=2))
        return 0

    init_db()
    result = await run_daily_suite()
    print(json.dumps(result, indent=2, default=str))
    failed = any(
        isinstance(v, dict) and v.get("status") == "FAILED"
        for v in result.values()
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
