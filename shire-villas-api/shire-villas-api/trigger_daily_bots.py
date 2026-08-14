import json
import os
import sys
import urllib.error
import urllib.request


def clean(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def main() -> int:
    api_url = clean(os.getenv("SHIRE_API_URL"))
    team_key = clean(os.getenv("TEAM_API_KEY"))

    if not api_url:
        print("ERROR: SHIRE_API_URL is missing.")
        return 2

    if not team_key:
        print("ERROR: TEAM_API_KEY is missing.")
        return 2

    url = f"{api_url}/bots/start/daily-suite"

    request = urllib.request.Request(
        url=url,
        method="POST",
        data=b"",
        headers={
            "X-Team-Key": team_key,
            "Content-Type": "application/json",
            "User-Agent": "Shire-Daily-Cron/5.5",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(f"HTTP {response.status}")
            print(body)

            if 200 <= response.status < 300:
                print("SUCCESS: Main Shire service accepted Daily Lead Suite.")
                return 0

            print("ERROR: Main Shire service rejected cron trigger.")
            return 1

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP ERROR {exc.code}")
        print(body)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
