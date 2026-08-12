import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are QBot, a warm and sharp qualification assistant for
Shire Villas - 18 ultra-luxury 4BHK villas in Siolim, North Goa, starting
at INR 10 Crore. Your job in this chat is to naturally find out:
1. Budget range
2. Who makes the buying decision (authority)
3. Why they want the property (second home, investment, relocation)
4. Timeline to purchase
5. Location/property fit

Ask ONE question at a time. Keep replies under 3 sentences. Be premium,
warm, and direct - never pushy. Do not claim availability of a specific
villa unless availability is supplied by the system.
"""


async def is_available() -> bool:
    return bool(settings.GROQ_API_KEY)


async def chat_with_ai(
    message: str,
    history: list[dict] | None = None,
) -> dict:
    if not settings.GROQ_API_KEY:
        return _fallback_reply(message)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Accept only normal chat roles/content from the browser.
    for turn in (history or [])[-12:]:
        role = turn.get("role")
        content = turn.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            messages.append(
                {"role": role, "content": content[:4000]}
            )

    messages.append({"role": "user", "content": message[:4000]})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}"
                },
                json={
                    "model": settings.GROQ_MODEL,
                    "messages": messages,
                    "temperature": 0.4,
                    "max_tokens": 300,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
            return {"reply": reply, "source": "groq"}

    except Exception:
        logger.exception("Groq request failed; using rule fallback.")
        return _fallback_reply(message)


def _fallback_reply(message: str) -> dict:
    m = message.lower()

    if any(w in m for w in ["budget", "price", "cost", "cr", "crore"]):
        reply = (
            "Shire Villas starts at INR 10 Crore for a 4BHK. "
            "What budget range are you considering: 10-15 Cr, "
            "15-20 Cr, or 20 Cr+?"
        )
    elif any(w in m for w in ["when", "timeline", "soon"]):
        reply = (
            "Are you looking to buy in the next 0-3 months, "
            "3-6 months, or are you still exploring?"
        )
    elif any(w in m for w in ["hi", "hello", "hey"]):
        reply = (
            "Hi! I'm QBot from Shire Villas, Siolim. "
            "Are you exploring a second home, an investment, "
            "or relocation to Goa?"
        )
    else:
        reply = (
            "Thanks for sharing that. Could you tell me your "
            "budget range and purchase timeline?"
        )

    return {"reply": reply, "source": "rule_based"}
