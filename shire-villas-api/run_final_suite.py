import asyncio
import json

from app.config import settings
from app.database import init_db
from app.services.lead_bot_service import run_final_execution_suite


async def main():
    init_db()
    if not (settings.TAVILY_API_KEY or settings.BRAVE_SEARCH_API_KEY):
        print(json.dumps({"status": "SKIPPED", "reason": "No web-search provider configured"}, indent=2))
        return 0
    result = await run_final_execution_suite()
    print(json.dumps(result, indent=2, default=str))
    discovery = result.get("discovery") or {}
    failed = any(
        isinstance(v, dict) and v.get("status") == "FAILED"
        for v in discovery.values()
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
