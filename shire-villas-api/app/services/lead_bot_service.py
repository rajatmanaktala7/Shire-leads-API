import asyncio
import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.bot import LeadBotRun
from app.models.lead import OrganicOpportunity, Partner
from app.services.organic_service import score_opportunity, suggested_response


BUYER_QUERIES = [
    '"looking to buy" villa Goa',
    '"want to buy" villa "North Goa"',
    '"looking for" "second home" Goa',
    '"buying a villa" Goa Siolim',
    '"need a villa" Goa buy',
    '"budget" "villa" Goa "crore"',
    'site:reddit.com "villa" "North Goa" buy',
    'site:reddit.com "second home" Goa property',
    'site:quora.com Goa villa buy second home',
    'site:linkedin.com/posts Goa villa "looking" buy',
    '"Siolim" villa "looking to buy"',
    '"Assagao" OR "Siolim" "second home" buyer',
]

NRI_QUERIES = [
    '"NRI" "buy property in Goa"',
    '"NRI" "second home" Goa villa',
    '"returning to India" Goa villa buy',
    '"investment property" Goa villa NRI',
]

BROKER_QUERIES = [
    '"luxury real estate" broker Goa',
    '"luxury property consultant" Goa',
    '"North Goa" luxury property broker',
    '"Goa" "channel partner" luxury real estate',
    '"luxury real estate" broker Delhi Goa',
    '"luxury property" broker Mumbai Goa',
]

GENERIC_NOISE = [
    "best villas", "top villas", "for rent", "holiday rental", "airbnb",
    "booking.com", "hotel", "resort booking", "travel package", "vacation rental",
    "property listing", "browse properties", "homes for sale", "developer offers",
]

BUYER_SIGNAL_TERMS = [
    "looking to buy", "want to buy", "planning to buy", "need a villa",
    "second home", "purchase", "buyer", "budget", "shortlist", "invest",
    "considering", "recommend", "which area", "which location",
]

FIRST_PERSON_TERMS = [
    "i am looking", "i'm looking", "we are looking", "my budget",
    "our budget", "i want", "we want", "i plan", "we plan",
]

LOCATION_TERMS = ["goa", "north goa", "siolim", "assagao", "vagator", "anjuna", "morjim"]


def _now():
    return datetime.now(timezone.utc)


def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _provider_name() -> str | None:
    pref = (settings.LEAD_BOT_PROVIDER or "auto").lower()
    if pref == "tavily" and settings.TAVILY_API_KEY:
        return "tavily"
    if pref == "brave" and settings.BRAVE_SEARCH_API_KEY:
        return "brave"
    if settings.TAVILY_API_KEY:
        return "tavily"
    if settings.BRAVE_SEARCH_API_KEY:
        return "brave"
    return None


async def _tavily_search(query: str, max_results: int) -> list[dict]:
    """
    Production-safe Tavily Search.

    Uses the same minimal request profile as the Railway diagnostic that is
    known to pass on the Researcher plan. Groq performs the second-stage
    semantic quality gate, so advanced search is unnecessary for lead hunting.
    """
    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }

    async with httpx.AsyncClient(timeout=35.0) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {(settings.TAVILY_API_KEY or '').strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if r.status_code >= 400:
            # Preserve Tavily's useful error body in bot history, but never secrets.
            raise RuntimeError(
                f"Tavily Search failed ({r.status_code}): {r.text[:600]}"
            )

        data = r.json()

    out = []
    for x in data.get("results", []):
        out.append({
            "title": x.get("title") or "",
            "url": x.get("url") or "",
            "content": x.get("content") or "",
            "provider_score": float(x.get("score") or 0),
        })
    return out

async def _brave_search(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": settings.BRAVE_SEARCH_API_KEY},
            params={
                "q": query,
                "count": min(max_results, 20),
                "country": "IN",
                "search_lang": "en",
                "safesearch": "strict",
                "freshness": "pw",
            },
        )
        r.raise_for_status()
        data = r.json()
    out = []
    for x in (data.get("web") or {}).get("results", []):
        out.append({
            "title": x.get("title") or "",
            "url": x.get("url") or "",
            "content": x.get("description") or "",
            "provider_score": 0.55,
        })
    return out



def tavily_key_diagnostics() -> dict:
    key = (settings.TAVILY_API_KEY or "").strip()
    return {
        "configured": bool(key),
        "prefix": (key[:9] + "…") if key else None,
        "length": len(key),
    }


async def tavily_connection_test() -> dict:
    key = (settings.TAVILY_API_KEY or "").strip()
    result = tavily_key_diagnostics()

    if not key:
        return {**result, "usage_test": "NOT_CONFIGURED", "search_test": "NOT_CONFIGURED"}

    headers = {"Authorization": f"Bearer {key}"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.get("https://api.tavily.com/usage", headers=headers)
            result["usage_status_code"] = r.status_code
            result["usage_test"] = "PASS" if r.status_code == 200 else "FAIL"
            if r.status_code != 200:
                result["usage_error"] = r.text[:500]
        except Exception as exc:
            result["usage_test"] = "ERROR"
            result["usage_error"] = str(exc)[:500]

        try:
            r = await client.post(
                "https://api.tavily.com/search",
                headers={**headers, "Content-Type": "application/json"},
                json={
                    "query": "luxury villa North Goa",
                    "search_depth": "basic",
                    "max_results": 1,
                },
            )
            result["search_status_code"] = r.status_code
            result["search_test"] = "PASS" if r.status_code == 200 else "FAIL"
            if r.status_code == 200:
                result["search_results"] = len(r.json().get("results", []))
            else:
                result["search_error"] = r.text[:500]
        except Exception as exc:
            result["search_test"] = "ERROR"
            result["search_error"] = str(exc)[:500]

    return result




async def tavily_production_search_test() -> dict:
    """Run the exact payload used by Buyer Hunter."""
    try:
        provider, results = "tavily", await _tavily_search(
            '"looking to buy" villa Goa',
            2,
        )
        return {
            "test": "PASS",
            "provider": provider,
            "results": len(results),
            "sample_titles": [r.get("title", "")[:160] for r in results[:2]],
        }
    except Exception as exc:
        return {
            "test": "FAIL",
            "error": str(exc)[:900],
        }


async def web_search(query: str, max_results: int | None = None) -> tuple[str, list[dict]]:
    provider = _provider_name()
    if not provider:
        raise RuntimeError(
            "No web-search provider configured. Add TAVILY_API_KEY "
            "(recommended) or BRAVE_SEARCH_API_KEY in Railway Variables."
        )
    limit = max_results or settings.LEAD_BOT_MAX_RESULTS_PER_QUERY
    if provider == "tavily":
        return provider, await _tavily_search(query, limit)
    return provider, await _brave_search(query, limit)


def candidate_quality(title: str, content: str, url: str, provider_score: float = 0) -> float:
    blob = f"{title} {content}".lower()
    score = score_opportunity(blob)

    # Strong intent boosts.
    if any(x in blob for x in FIRST_PERSON_TERMS):
        score += 18
    if sum(1 for x in BUYER_SIGNAL_TERMS if x in blob) >= 2:
        score += 10
    if any(x in blob for x in LOCATION_TERMS):
        score += 8

    # Search-provider relevance can add up to 8 points.
    score += min(max(provider_score, 0), 1) * 8

    # Reduce generic SEO/listing/travel noise.
    if any(x in blob for x in GENERIC_NOISE):
        score -= 24

    domain = _domain(url)
    if domain in {"reddit.com", "quora.com", "linkedin.com"}:
        score += 6

    # A source URL is mandatory for an automated discovery.
    if not url:
        score -= 30

    return round(max(0, min(score, 100)), 1)


def infer_hints(text: str) -> dict:
    blob = text.lower()
    loc = None
    for x in ["siolim", "assagao", "vagator", "anjuna", "morjim", "north goa", "goa"]:
        if x in blob:
            loc = x.title()
            break

    budget = None
    m = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:cr|crore)", blob)
    if m:
        budget = f"{m.group(1)} Cr"

    timeline = None
    for t in ["immediate", "this month", "0-3 months", "3 months", "3-6 months", "6-12 months"]:
        if t in blob:
            timeline = t
            break

    return {"location": loc, "budget_hint": budget, "timeline_hint": timeline}


def _dedupe_opportunity(db: Session, url: str, source_text: str) -> bool:
    if url and db.query(OrganicOpportunity).filter(OrganicOpportunity.source_url == url).first():
        return True

    # Conservative duplicate check on the beginning of source text.
    prefix = (source_text or "")[:220]
    if prefix:
        existing = (
            db.query(OrganicOpportunity)
            .filter(OrganicOpportunity.source_text.like(prefix[:140] + "%"))
            .first()
        )
        if existing:
            return True
    return False


async def _ai_quality_gate(text: str, rule_score: float) -> tuple[float, str | None]:
    """
    Optional Groq refinement. It never creates outreach; it only adjusts the
    opportunity score. If Groq is unavailable or parsing fails, rule score wins.
    """
    if not settings.GROQ_API_KEY or rule_score < 45:
        return rule_score, None

    system = (
        "You are a luxury-real-estate lead-quality analyst for Shire Villas, "
        "an ultra-luxury villa project in Siolim, North Goa. Judge whether the "
        "public web snippet indicates a genuine prospective BUYER or investment "
        "researcher, not a generic article, travel/rental query, seller listing, "
        "or property advertisement. Return ONLY compact JSON with keys "
        "buyer_intent (true/false), confidence (0-100), reason (max 120 chars)."
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text[:5000]},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 120,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return rule_score, None
        data = json.loads(match.group(0))
        confidence = float(data.get("confidence") or 0)
        if not data.get("buyer_intent"):
            return min(rule_score, 54), str(data.get("reason") or "")
        blended = rule_score * 0.55 + confidence * 0.45
        return round(min(100, blended), 1), str(data.get("reason") or "")
    except Exception:
        return rule_score, None


async def run_buyer_hunter(
    queries: list[str] | None = None,
    bot_name: str = "Buyer Intent Hunter",
) -> dict:
    db = SessionLocal()
    run = LeadBotRun(bot_name=bot_name, status="RUNNING")
    db.add(run)
    db.commit()
    db.refresh(run)

    created = duplicates = low_quality = seen = qcount = 0
    provider_used = None
    errors = []

    try:
        for query in (queries or BUYER_QUERIES):
            qcount += 1
            try:
                provider, results = await web_search(query)
                provider_used = provider
            except Exception as exc:
                errors.append(f"{query}: {exc}")
                continue

            for item in results:
                seen += 1
                text = f"{item['title']}. {item['content']}".strip()
                rule_score = candidate_quality(
                    item["title"], item["content"], item["url"], item["provider_score"]
                )
                final_score, ai_reason = await _ai_quality_gate(text, rule_score)

                if final_score < settings.LEAD_BOT_MIN_SCORE:
                    low_quality += 1
                    continue
                if _dedupe_opportunity(db, item["url"], text):
                    duplicates += 1
                    continue

                hints = infer_hints(text)
                opp = OrganicOpportunity(
                    platform=f"ai_web:{_domain(item['url']) or provider}",
                    source_url=item["url"],
                    source_text=text[:8000],
                    location=hints["location"],
                    budget_hint=hints["budget_hint"],
                    timeline_hint=hints["timeline_hint"],
                    intent_type="BUYER_INTENT",
                    intent_score=final_score,
                    notes=(
                        f"Auto-discovered by {bot_name}. "
                        + (f"AI quality gate: {ai_reason}" if ai_reason else "")
                    )[:1800],
                )
                db.add(opp)
                db.flush()
                opp.suggested_response = suggested_response(opp)
                db.commit()
                created += 1

        run.status = "SUCCESS" if not errors else ("PARTIAL" if created else "FAILED")
    except Exception as exc:
        errors.append(str(exc))
        run.status = "FAILED"
    finally:
        run.provider = provider_used
        run.queries_run = qcount
        run.results_seen = seen
        run.opportunities_created = created
        run.duplicates_skipped = duplicates
        run.low_quality_skipped = low_quality
        run.error_text = "\n".join(errors)[-5000:] if errors else None
        run.completed_at = _now()
        db.commit()
        result = {
            "run_id": run.id,
            "bot": bot_name,
            "provider": provider_used,
            "status": run.status,
            "queries_run": qcount,
            "results_seen": seen,
            "opportunities_created": created,
            "duplicates_skipped": duplicates,
            "low_quality_skipped": low_quality,
            "errors": errors[:5],
        }
        db.close()
        return result


def _partner_exists(db: Session, website: str, name: str) -> bool:
    clauses = []
    if website:
        clauses.append(Partner.website == website)
    if name:
        clauses.append(Partner.name == name)
    return bool(clauses and db.query(Partner).filter(or_(*clauses)).first())


async def run_broker_hunter() -> dict:
    db = SessionLocal()
    run = LeadBotRun(bot_name="Broker & Channel Partner Hunter", status="RUNNING")
    db.add(run)
    db.commit()
    db.refresh(run)

    created = duplicates = seen = qcount = 0
    provider_used = None
    errors = []

    try:
        for query in BROKER_QUERIES:
            qcount += 1
            try:
                provider, results = await web_search(query)
                provider_used = provider
            except Exception as exc:
                errors.append(f"{query}: {exc}")
                continue

            for item in results:
                seen += 1
                title = re.sub(r"\s*[|–—-].*$", "", item["title"]).strip() or item["title"]
                website = item["url"]
                if _partner_exists(db, website, title):
                    duplicates += 1
                    continue

                text = f"{item['title']} {item['content']}".lower()
                score = 45
                if "luxury" in text:
                    score += 20
                if "goa" in text or "north goa" in text:
                    score += 20
                if "broker" in text or "consultant" in text or "real estate" in text:
                    score += 10
                if any(x in text for x in ["villa", "second home", "hnI".lower(), "nri"]):
                    score += 5

                if score < 70:
                    continue

                partner = Partner(
                    name=title[:240],
                    company=title[:240],
                    partner_type="broker",
                    city="Goa" if "goa" in text else None,
                    website=website,
                    specialization="Luxury real estate / villa channel partner",
                    score=min(score, 100),
                    notes=f"Auto-discovered from public web search. {item['content'][:900]}",
                )
                db.add(partner)
                db.commit()
                created += 1

        run.status = "SUCCESS" if not errors else ("PARTIAL" if created else "FAILED")
    except Exception as exc:
        errors.append(str(exc))
        run.status = "FAILED"
    finally:
        run.provider = provider_used
        run.queries_run = qcount
        run.results_seen = seen
        run.partners_created = created
        run.duplicates_skipped = duplicates
        run.error_text = "\n".join(errors)[-5000:] if errors else None
        run.completed_at = _now()
        db.commit()
        result = {
            "run_id": run.id,
            "bot": "Broker & Channel Partner Hunter",
            "provider": provider_used,
            "status": run.status,
            "queries_run": qcount,
            "results_seen": seen,
            "partners_created": created,
            "duplicates_skipped": duplicates,
            "errors": errors[:5],
        }
        db.close()
        return result


async def run_daily_suite() -> dict:
    buyer = await run_buyer_hunter()
    nri = await run_buyer_hunter(NRI_QUERIES, bot_name="NRI Second-Home Hunter")
    broker = await run_broker_hunter()
    return {
        "status": "completed",
        "buyer_hunter": buyer,
        "nri_hunter": nri,
        "broker_hunter": broker,
    }


def latest_runs(db: Session, limit: int = 20) -> list[LeadBotRun]:
    return (
        db.query(LeadBotRun)
        .order_by(LeadBotRun.started_at.desc())
        .limit(limit)
        .all()
    )
