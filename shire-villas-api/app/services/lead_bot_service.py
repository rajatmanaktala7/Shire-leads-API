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
from app.services.organic_service import suggested_response
from app.services.lead_intelligence_service import (
    ai_classify,
    apollo_enrich,
    build_intelligence_payload,
    deterministic_score,
    domain,
    dump_intelligence_notes,
    enrich_candidate,
    extract_contacts,
    fetch_public_page_contacts,
    resolve_buyer_identity,
)


BUYER_DISCOVERY_SPECS = [
    {"query": '"looking to buy" "villa" "Goa"', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"want to buy" "villa" "Goa"', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"buy a villa" "North Goa"', "domains": ["quora.com"], "time_range": "year"},
    {"query": '"second home" "Goa" "buy"', "domains": ["quora.com"], "time_range": "year"},
    {"query": '"looking to buy" "Goa" "villa"', "domains": ["linkedin.com"], "time_range": "year"},
    {"query": '"planning to buy" "Goa" "property"', "domains": ["linkedin.com"], "time_range": "year"},
    {"query": '"my budget" "Goa" "villa" crore', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"my budget" "Goa" property crore', "domains": ["quora.com"], "time_range": "year"},
    {"query": '"moving to Goa" "buy" "villa"', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"retiring in Goa" "buy" property', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"recommend a villa" "North Goa" buy', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"recommend a villa" "North Goa" buy', "domains": ["quora.com"], "time_range": "year"},
]

BUYER_QUERIES = [x["query"] for x in BUYER_DISCOVERY_SPECS]


NRI_DISCOVERY_SPECS = [
    {"query": '"NRI" "looking to buy" "Goa" villa', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"NRI" "second home" "Goa" buy', "domains": ["quora.com"], "time_range": "year"},
    {"query": '"returning to India" "Goa" "buy" property', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"overseas Indian" "buy property" Goa', "domains": ["quora.com"], "time_range": "year"},
    {"query": '"NRI" "Goa" villa "budget" crore', "domains": ["reddit.com"], "time_range": "year"},
    {"query": '"NRI" "Goa" property "budget" crore', "domains": ["linkedin.com"], "time_range": "year"},
]

NRI_QUERIES = [x["query"] for x in NRI_DISCOVERY_SPECS]


BROKER_QUERIES = [
    '"luxury real estate" broker Goa',
    '"luxury property consultant" Goa',
    '"North Goa" luxury property broker',
    '"Goa" "channel partner" luxury real estate',
    '"luxury real estate" broker Delhi Goa',
    '"luxury property" broker Mumbai Goa',
    '"NRI property consultant" Goa',
    '"family office" real estate Goa advisor',
]


NOISE_CLASSES = {
    "DEVELOPER", "PROPERTY_LISTING", "NEWS", "BLOG", "MARKET_REPORT",
    "GENERIC_SOCIAL_CONTENT", "UNKNOWN", "BROKER", "CHANNEL_PARTNER",
}


def _now():
    return datetime.now(timezone.utc)


def _provider_name() -> str | None:
    pref = (settings.LEAD_BOT_PROVIDER or "auto").strip().lower()
    if pref == "tavily" and settings.TAVILY_API_KEY:
        return "tavily"
    if pref == "brave" and settings.BRAVE_SEARCH_API_KEY:
        return "brave"
    if settings.TAVILY_API_KEY:
        return "tavily"
    if settings.BRAVE_SEARCH_API_KEY:
        return "brave"
    return None


async def _tavily_search(
    query: str,
    max_results: int,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    time_range: str | None = None,
    advanced: bool = False,
) -> list[dict]:
    payload = {
        "query": query,
        "search_depth": "advanced" if advanced else "basic",
        "max_results": max_results,
        "include_raw_content": "text" if advanced else False,
    }
    if advanced:
        payload["chunks_per_source"] = 3
    if include_domains:
        payload["include_domains"] = include_domains
    if exclude_domains:
        payload["exclude_domains"] = exclude_domains
    if time_range in {"day", "week", "month", "year", "d", "w", "m", "y"}:
        payload["time_range"] = time_range

    async with httpx.AsyncClient(timeout=45.0) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            headers={
                "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Tavily Search failed ({r.status_code}): {r.text[:600]}")
        data = r.json()

    return [
        {
            "title": x.get("title") or "",
            "url": x.get("url") or "",
            "content": x.get("content") or "",
            "raw_content": x.get("raw_content") or "",
            "provider_score": float(x.get("score") or 0),
            "published_date": x.get("published_date"),
        }
        for x in data.get("results", [])
        if float(x.get("score") or 0) >= 0.45
    ]


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
    return [
        {
            "title": x.get("title") or "",
            "url": x.get("url") or "",
            "content": x.get("description") or "",
            "provider_score": 0.55,
        }
        for x in (data.get("web") or {}).get("results", [])
    ]


async def web_search(
    query: str,
    max_results: int | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    time_range: str | None = None,
    advanced: bool = False,
) -> tuple[str, list[dict]]:
    provider = _provider_name()
    if not provider:
        raise RuntimeError("No web-search provider configured. Add TAVILY_API_KEY or BRAVE_SEARCH_API_KEY.")
    limit = max_results or settings.LEAD_BOT_MAX_RESULTS_PER_QUERY
    if provider == "tavily":
        return provider, await _tavily_search(
            query,
            limit,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            time_range=time_range,
            advanced=advanced,
        )
    return provider, await _brave_search(query, limit)


def tavily_key_diagnostics() -> dict:
    key = (settings.TAVILY_API_KEY or "").strip()
    return {"configured": bool(key), "prefix": (key[:9] + "…") if key else None, "length": len(key)}


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
                json={"query": '"looking to buy" villa Goa', "search_depth": "basic", "max_results": 1},
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
    try:
        results = await _tavily_search('"looking to buy" villa Goa', 2)
        return {"test": "PASS", "provider": "tavily", "results": len(results), "sample_titles": [x["title"][:160] for x in results]}
    except Exception as exc:
        return {"test": "FAIL", "error": str(exc)[:900]}


def _dedupe_opportunity(db: Session, url: str, source_text: str) -> bool:
    if url and db.query(OrganicOpportunity).filter(OrganicOpportunity.source_url == url).first():
        return True
    prefix = (source_text or "")[:180]
    if prefix and db.query(OrganicOpportunity).filter(OrganicOpportunity.source_text.like(prefix[:120] + "%")).first():
        return True
    return False


def _lead_score_with_ai(text: str, classification: str, enrichment: dict, ai: dict) -> dict:
    score = deterministic_score(text, classification, enrichment.get("phone"), enrichment.get("email"))
    # Preserve deterministic explainability while allowing AI-extracted questionnaire hints.
    if ai.get("budget_hint") and not score.get("budget_hint"):
        score["budget_hint"] = ai["budget_hint"]
    if ai.get("timeline_hint") and not score.get("timeline_hint"):
        score["timeline_hint"] = ai["timeline_hint"]
    if ai.get("purpose") and not score.get("purpose"):
        score["purpose"] = ai["purpose"]
    if ai.get("authority") and not score.get("authority_hint"):
        score["authority_hint"] = ai["authority"]
    if ai.get("location") and not score.get("location"):
        score["location"] = ai["location"]
    return score


async def run_buyer_hunter(
    queries: list[str] | None = None,
    bot_name: str = "Buyer Intent Hunter",
    specs: list[dict] | None = None,
) -> dict:
    db = SessionLocal()
    run = LeadBotRun(bot_name=bot_name, status="RUNNING")
    db.add(run); db.commit(); db.refresh(run)

    created = duplicates = low_quality = seen = qcount = 0
    provider_used = None
    errors: list[str] = []
    classified_noise = no_identity = no_contact = identity_resolved = intent_verified = 0

    if specs is None:
        if bot_name == "NRI Second-Home Hunter":
            specs = NRI_DISCOVERY_SPECS
        elif queries:
            specs = [{"query": q, "domains": None, "time_range": "year"} for q in queries]
        else:
            specs = BUYER_DISCOVERY_SPECS

    try:
        for spec in specs:
            query = spec["query"]
            qcount += 1
            try:
                provider, results = await web_search(
                    query,
                    include_domains=spec.get("domains"),
                    time_range=spec.get("time_range") or "year",
                    advanced=True,
                )
                provider_used = provider
            except Exception as exc:
                errors.append(f"{query}: {exc}")
                continue

            for item in results:
                seen += 1
                raw = item.get("raw_content") or ""
                text = f"{item['title']}. {item['content']} {raw[:6000]}".strip()

                if _dedupe_opportunity(db, item["url"], text):
                    duplicates += 1
                    continue

                ai = await ai_classify(item["title"], text, item["url"])
                ai = await resolve_buyer_identity(item["title"], text, item["url"], ai)

                classification = ai["classification"]
                if classification in NOISE_CLASSES:
                    classified_noise += 1
                    low_quality += 1
                    continue

                if not ai.get("buyer_intent"):
                    low_quality += 1
                    continue
                intent_verified += 1

                person_name = ai.get("person_name")
                if not person_name:
                    no_identity += 1
                    low_quality += 1
                    continue
                identity_resolved += 1

                enrichment = await enrich_candidate(item["title"], text, item["url"], ai)
                if not enrichment.get("contact_attributable"):
                    no_contact += 1
                    low_quality += 1
                    continue

                score = _lead_score_with_ai(text, classification, enrichment, ai)
                intel = build_intelligence_payload(item["title"], item["url"], ai, score, enrichment)

                if intel.get("band") in {"REJECT", "IDENTITY_REQUIRED", "CONTACT_ENRICHMENT_REQUIRED"}:
                    low_quality += 1
                    continue

                # Minimum admission remains deliberately lower than CRM-ready.
                # This lets a named, contactable buyer enter qualification even if
                # budget/timeline still need a human/AI conversation.
                if score["total"] < settings.LEAD_BOT_MIN_ADMISSION_SCORE:
                    low_quality += 1
                    continue

                opp = OrganicOpportunity(
                    person_name=person_name,
                    brand_company=ai.get("company") or (enrichment.get("apollo") or {}).get("organization"),
                    phone=enrichment.get("phone"),
                    email=enrichment.get("email"),
                    platform=f"ai_web:{domain(item['url']) or provider}",
                    source_url=item["url"],
                    source_text=text[:8000],
                    location=ai.get("location") or score.get("location"),
                    budget_hint=ai.get("budget_hint") or score.get("budget_hint"),
                    timeline_hint=ai.get("timeline_hint") or score.get("timeline_hint"),
                    intent_type=intel["band"],
                    intent_score=score["total"],
                    verified=True,
                    notes=dump_intelligence_notes(intel, f"Auto-discovered by {bot_name} V6.2."),
                )
                db.add(opp); db.flush()
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
            "noise_rejected": classified_noise,
            "identity_resolved": identity_resolved,
            "identity_missing_rejected": no_identity,
            "buyer_intent_verified": intent_verified,
            "qualified_without_contact": no_contact,
            "errors": errors[:5],
        }
        db.close()
        return result


def _partner_exists(db: Session, website: str, name: str) -> bool:
    clauses = []
    if website: clauses.append(Partner.website == website)
    if name: clauses.append(Partner.name == name)
    return bool(clauses and db.query(Partner).filter(or_(*clauses)).first())


async def run_broker_hunter() -> dict:
    db = SessionLocal()
    run = LeadBotRun(bot_name="Broker & Channel Partner Hunter", status="RUNNING")
    db.add(run); db.commit(); db.refresh(run)
    created = duplicates = seen = qcount = 0
    provider_used = None
    errors: list[str] = []
    try:
        for query in BROKER_QUERIES:
            qcount += 1
            try:
                provider, results = await web_search(query)
                provider_used = provider
            except Exception as exc:
                errors.append(f"{query}: {exc}"); continue
            for item in results:
                seen += 1
                title = re.sub(r"\s*[|–—-].*$", "", item["title"]).strip() or item["title"]
                website = item["url"]
                if _partner_exists(db, website, title):
                    duplicates += 1; continue
                text = f"{item['title']} {item['content']}"
                b = text.lower()
                score = 0
                if "luxury" in b: score += 25
                if "goa" in b or "north goa" in b: score += 25
                if any(x in b for x in ["broker", "consultant", "real estate", "channel partner"]): score += 30
                if any(x in b for x in ["villa", "second home", "hni", "nri", "family office"]): score += 20
                if any(x in b for x in ["news", "market report", "our project", "developer", "villas for sale", "property listing"]):
                    continue
                if score < 85: continue
                source_contacts = extract_contacts(text)
                page_contacts = await fetch_public_page_contacts(website)
                phones = source_contacts["phones"] + [x for x in page_contacts["phones"] if x not in source_contacts["phones"]]
                emails = source_contacts["emails"] + [x for x in page_contacts["emails"] if x not in source_contacts["emails"]]
                apollo = await apollo_enrich(None, emails[0] if emails else None, domain(website))
                phone = phones[0] if phones else apollo.get("phone")
                email = emails[0] if emails else apollo.get("email")
                if not phone and not email:
                    continue
                partner = Partner(
                    name=title[:240], company=title[:240], partner_type="broker",
                    city="Goa" if "goa" in b else None, phone=phone, email=email,
                    website=website, specialization="Luxury real estate / villa channel partner",
                    score=min(score, 100),
                    notes=("Auto-discovered from public web search. " + item["content"][:1000])[:3900],
                )
                db.add(partner); db.commit(); created += 1
        run.status = "SUCCESS" if not errors else ("PARTIAL" if created else "FAILED")
    except Exception as exc:
        errors.append(str(exc)); run.status = "FAILED"
    finally:
        run.provider = provider_used; run.queries_run = qcount; run.results_seen = seen
        run.partners_created = created; run.duplicates_skipped = duplicates
        run.error_text = "\n".join(errors)[-5000:] if errors else None
        run.completed_at = _now(); db.commit()
        result = {"run_id": run.id, "bot": "Broker & Channel Partner Hunter", "provider": provider_used,
                  "status": run.status, "queries_run": qcount, "results_seen": seen,
                  "partners_created": created, "duplicates_skipped": duplicates, "errors": errors[:5]}
        db.close(); return result


async def run_daily_suite() -> dict:
    buyer = await run_buyer_hunter()
    nri = await run_buyer_hunter(bot_name="NRI Second-Home Hunter", specs=NRI_DISCOVERY_SPECS)
    broker = await run_broker_hunter()
    return {"status": "completed", "buyer_hunter": buyer, "nri_hunter": nri, "broker_hunter": broker}


def latest_runs(db: Session, limit: int = 20) -> list[LeadBotRun]:
    return db.query(LeadBotRun).order_by(LeadBotRun.started_at.desc()).limit(limit).all()
