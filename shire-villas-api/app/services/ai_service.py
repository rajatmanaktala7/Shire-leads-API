import httpx

from app.config import settings

SYSTEM_PROMPT = """You are QBot, a warm and sharp qualification assistant for
Shire Villas — 18 ultra-luxury 4BHK villas in Siolim, North Goa, starting
at ₹10 Crore. Your job in this chat is to naturally find out:
1. Budget range
2. Who makes the buying decision (authority)
3. Why they want the property (need: second home, investment, relocation)
4. Timeline to purchase
5. Location/property fit

Ask ONE question at a time. Keep replies under 3 sentences. Be premium,
warm, and direct — never pushy or salesy. Once you have enough info,
say clearly "QUALIFICATION_COMPLETE" at the end of your message along
with a one-line summary.
"""


async def is_available() -> bool:
    return bool(settings.GROQ_API_KEY)


async def chat_with_ai(message: str, history: list[dict] | None = None) -> dict:
    """
    Calls Groq's OpenAI-compatible chat endpoint. If no API key is set,
    or the call fails for any reason, falls back to a deterministic
    rule-based reply so the product NEVER breaks in front of a user.
    """
    if not settings.GROQ_API_KEY:
        return _fallback_reply(message)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or []):
        messages.append(turn)
    messages.append({"role": "user", "content": message})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
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
    except Exception as exc:  # noqa: BLE001 — deliberate broad catch, this must never 500
        fallback = _fallback_reply(message)
        fallback["error"] = str(exc)
        return fallback


def _fallback_reply(message: str) -> dict:
    """Simple deterministic script used when AI is offline/unconfigured."""
    m = message.lower()
    if any(w in m for w in ["budget", "price", "cost", "cr", "crore"]):
        reply = (
            "Shire Villas starts at ₹10 Crore for a 4BHK. "
            "What budget range are you considering — 10-15 Cr, 15-20 Cr, or 20 Cr+?"
        )
    elif any(w in m for w in ["when", "timeline", "soon"]):
        reply = "Good to know. Are you looking to buy in the next 0-3 months, 3-6 months, or just exploring for now?"
    elif any(w in m for w in ["hi", "hello", "hey"]):
        reply = "Hi! I'm QBot from Shire Villas, Siolim. Are you exploring a second home, an investment, or relocation to Goa?"
    else:
        reply = (
            "Thanks for sharing that. Could you tell me a bit about your budget range "
            "and timeline, so I can point you to the right villa unit?"
        )
    return {"reply": reply, "source": "rule_based"}
