import json
import re
from html import unescape
from urllib.parse import urlparse

import httpx

from app.config import settings


CONTENT_CLASSES = {
    "REAL_BUYER",
    "POSSIBLE_BUYER",
    "BROKER",
    "CHANNEL_PARTNER",
    "DEVELOPER",
    "PROPERTY_LISTING",
    "NEWS",
    "BLOG",
    "MARKET_REPORT",
    "GENERIC_SOCIAL_CONTENT",
    "UNKNOWN",
}

LISTING_DOMAINS = {
    "magicbricks.com", "99acres.com", "housing.com", "commonfloor.com", "sothebysrealty.com",
}
NEWS_DOMAINS = {"cntraveller.in", "timesofindia.indiatimes.com"}

SOCIAL_DOMAINS = {
    "linkedin.com", "reddit.com", "quora.com", "instagram.com", "facebook.com", "youtube.com",
}

BUYING_PHRASES = [
    "looking to buy", "want to buy", "planning to buy", "need a villa", "need property",
    "looking for a villa", "looking for property", "planning to purchase", "want to purchase",
    "buy a villa", "buy property", "second home", "shortlisting", "budget is", "my budget",
    "our budget", "recommend a villa", "recommend property", "considering buying",
]

FIRST_PERSON = [
    "i am looking", "i'm looking", "we are looking", "i want", "we want", "i plan", "we plan",
    "my budget", "our budget", "for my family", "for ourselves", "i am considering",
]

NOISE_PHRASES = [
    "for sale", "property listing", "browse properties", "luxury villas for sale", "project overview",
    "developer", "book now", "holiday rental", "vacation rental", "airbnb", "hotel", "resort",
    "market report", "real estate trends", "why investors", "why nris", "top villas", "best villas",
]

EMAIL_RE = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")


def domain(url: str | None) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _clean_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if len(digits) == 10:
        return "+91" + digits
    return raw.strip()


def extract_contacts(text: str) -> dict:
    text = unescape(text or "")
    emails = []
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".,;:()[]<>\"'")
        if e not in emails:
            emails.append(e)
    phones = []
    for p in PHONE_RE.findall(text):
        p = _clean_phone(p)
        if p not in phones:
            phones.append(p)
    return {"emails": emails[:5], "phones": phones[:5]}


def infer_budget(text: str) -> str | None:
    blob = (text or "").lower().replace(",", "")
    patterns = [
        r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:cr|crore)",
        r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:cr|crore)",
    ]
    m = re.search(patterns[0], blob)
    if m:
        return f"{m.group(1)}-{m.group(2)} Cr"
    m = re.search(patterns[1], blob)
    if m:
        return f"{m.group(1)} Cr"
    return None


def infer_timeline(text: str) -> str | None:
    b = (text or "").lower()
    rules = [
        ("0-3 months", ["immediately", "immediate", "this month", "next month", "0-3 months", "within 3 months"]),
        ("3-6 months", ["3-6 months", "within 6 months", "next 6 months"]),
        ("6-12 months", ["6-12 months", "within a year", "this year", "next year"]),
        ("Exploring", ["exploring", "researching", "considering", "no rush"]),
    ]
    for value, terms in rules:
        if any(t in b for t in terms):
            return value
    return None


def infer_location(text: str) -> str | None:
    b = (text or "").lower()
    for loc in ["Siolim", "Assagao", "Vagator", "Morjim", "Anjuna", "North Goa", "Goa"]:
        if loc.lower() in b:
            return loc
    return None


def infer_purpose(text: str) -> str | None:
    b = (text or "").lower()
    if "second home" in b or "holiday home" in b:
        return "Second Home"
    if "relocat" in b or "moving to goa" in b or "retir" in b:
        return "Relocation"
    if "invest" in b or "rental yield" in b or "appreciation" in b:
        return "Investment"
    if "own use" in b or "for my family" in b:
        return "Own Use"
    return None


def infer_authority(text: str) -> str | None:
    b = (text or "").lower()
    if any(x in b for x in ["my wife and i", "my husband and i", "with family", "jointly"]):
        return "Joint decision"
    if any(x in b for x in ["i want", "i am looking", "my budget", "i plan"]):
        return "Likely principal"
    return None


def classify_rule_based(title: str, text: str, url: str) -> str:
    b = f"{title} {text}".lower()
    d = domain(url)
    first_person = any(x in b for x in FIRST_PERSON)
    buying = any(x in b for x in BUYING_PHRASES)
    if (first_person and buying) or (first_person and "goa" in b and any(x in b for x in ["villa", "property", "home"])):
        return "REAL_BUYER"
    if d in SOCIAL_DOMAINS and buying and "goa" in b:
        return "POSSIBLE_BUYER"
    if any(x in b for x in ["broker", "channel partner", "real estate consultant", "property consultant"]):
        return "BROKER"
    if d in NEWS_DOMAINS or any(x in b for x in ["news", "report", "trend", "market", "why nris", "why investors"]):
        return "NEWS"
    if d in LISTING_DOMAINS or "property listing" in b or "villas for sale" in b:
        return "PROPERTY_LISTING"
    if any(x in b for x in ["developer", "projects", "our villas", "our project"]):
        return "DEVELOPER"
    if any(x in b for x in NOISE_PHRASES):
        return "BLOG"
    return "UNKNOWN"


def deterministic_score(text: str, classification: str, phone: str | None = None, email: str | None = None) -> dict:
    b = (text or "").lower()
    # 25 purchase intent
    if any(x in b for x in FIRST_PERSON) and any(x in b for x in BUYING_PHRASES):
        intent = 25
    elif any(x in b for x in ["looking to buy", "want to buy", "need a villa", "planning to buy"]):
        intent = 22
    elif any(x in b for x in BUYING_PHRASES):
        intent = 14
    else:
        intent = 0

    # 20 budget fit
    budget_hint = infer_budget(b)
    budget = 5 if budget_hint is None else 0
    if budget_hint:
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", budget_hint)]
        top = max(nums) if nums else 0
        if top >= 10:
            budget = 20
        elif top >= 8:
            budget = 18
        elif top >= 6:
            budget = 10
        else:
            budget = 0

    # 15 location/property fit
    if "siolim" in b and "villa" in b:
        fit = 15
    elif any(x in b for x in ["assagao", "vagator", "morjim", "anjuna"]) and "villa" in b:
        fit = 13
    elif "north goa" in b and "villa" in b:
        fit = 12
    elif "goa" in b and any(x in b for x in ["villa", "second home", "property"]):
        fit = 8
    else:
        fit = 0

    # 15 timeline
    timeline_hint = infer_timeline(b)
    timeline_map = {"0-3 months": 15, "3-6 months": 12, "6-12 months": 9, "Exploring": 2, None: 0}
    timeline = timeline_map[timeline_hint]

    # 10 purpose
    purpose = infer_purpose(b)
    purpose_map = {"Second Home": 10, "Own Use": 10, "Relocation": 10, "Investment": 8, None: 0}
    need = purpose_map[purpose]

    # 5 authority
    authority_hint = infer_authority(b)
    authority = 5 if authority_hint == "Likely principal" else 4 if authority_hint == "Joint decision" else 0

    # 10 contactability
    contactability = 10 if phone and email else 9 if phone else 8 if email else 0

    score = intent + budget + fit + timeline + need + authority + contactability
    if classification not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        score = min(score, 49)
    return {
        "purchase_intent": intent,
        "budget": budget,
        "location_fit": fit,
        "timeline": timeline,
        "need": need,
        "authority": authority,
        "contactability": contactability,
        "total": round(min(100, score), 1),
        "budget_hint": budget_hint,
        "timeline_hint": timeline_hint,
        "purpose": purpose,
        "authority_hint": authority_hint,
        "location": infer_location(b),
    }


async def ai_classify(title: str, text: str, url: str) -> dict:
    fallback = {
        "classification": classify_rule_based(title, text, url),
        "person_name": None,
        "company": None,
        "buyer_intent": False,
        "confidence": 55,
        "reason": "Rule-based classification",
        "budget_hint": infer_budget(text),
        "timeline_hint": infer_timeline(text),
        "purpose": infer_purpose(text),
        "authority": infer_authority(text),
        "location": infer_location(text),
    }
    fallback["buyer_intent"] = fallback["classification"] in {"REAL_BUYER", "POSSIBLE_BUYER"}
    if not settings.GROQ_API_KEY:
        return fallback

    system = """You are Shire Villas' buyer-intelligence classifier. Shire sells ultra-luxury 4BHK villas in Siolim, North Goa, starting around INR 10 crore. Classify PUBLIC WEB evidence, not topical similarity. A news article, developer page, listing portal, SEO blog, generic social reel, or market report is NEVER a buyer lead. A buyer lead requires evidence that an identifiable person is personally considering, asking about, or planning a property purchase. Return ONLY valid JSON with keys: classification, person_name, company, buyer_intent, confidence, reason, budget_hint, timeline_hint, purpose, authority, location. classification must be one of REAL_BUYER,POSSIBLE_BUYER,BROKER,CHANNEL_PARTNER,DEVELOPER,PROPERTY_LISTING,NEWS,BLOG,MARKET_REPORT,GENERIC_SOCIAL_CONTENT,UNKNOWN. Never invent a person, company, budget, timeline, phone, or email. Use null when not evidenced."""
    payload = f"TITLE: {title}\nURL: {url}\nPUBLIC TEXT:\n{text[:6000]}"
    try:
        async with httpx.AsyncClient(timeout=18.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                json={
                    "model": settings.GROQ_MODEL,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": payload}],
                    "temperature": 0.0,
                    "max_tokens": 350,
                },
            )
            r.raise_for_status()
            raw = r.json()["choices"][0]["message"]["content"]
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return fallback
        data = json.loads(m.group(0))
        cls = str(data.get("classification") or fallback["classification"]).upper()
        if cls not in CONTENT_CLASSES:
            cls = fallback["classification"]
        return {
            "classification": cls,
            "person_name": data.get("person_name") or None,
            "company": data.get("company") or None,
            "buyer_intent": bool(data.get("buyer_intent")) and cls in {"REAL_BUYER", "POSSIBLE_BUYER"},
            "confidence": max(0, min(100, float(data.get("confidence") or 0))),
            "reason": str(data.get("reason") or "")[:500],
            "budget_hint": data.get("budget_hint") or fallback["budget_hint"],
            "timeline_hint": data.get("timeline_hint") or fallback["timeline_hint"],
            "purpose": data.get("purpose") or fallback["purpose"],
            "authority": data.get("authority") or fallback["authority"],
            "location": data.get("location") or fallback["location"],
        }
    except Exception:
        return fallback


async def fetch_public_page_contacts(url: str) -> dict:
    d = domain(url)
    if not url or d in SOCIAL_DOMAINS:
        return {"emails": [], "phones": [], "source": None}
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 ShireLeadBot/6.0"}) as client:
            r = await client.get(url)
            if r.status_code >= 400 or "text/html" not in r.headers.get("content-type", ""):
                return {"emails": [], "phones": [], "source": None}
            c = extract_contacts(r.text[:500000])
            return {**c, "source": url if (c["emails"] or c["phones"]) else None}
    except Exception:
        return {"emails": [], "phones": [], "source": None}


async def tavily_contact_lookup(person_name: str | None, company: str | None, source_url: str | None) -> dict:
    if not settings.TAVILY_API_KEY or not (person_name or company):
        return {"emails": [], "phones": [], "evidence_urls": []}
    terms = [x for x in [person_name, company] if x]
    q = ' "'.join(terms)
    q = f'"{q}" contact phone email'
    payload = {"query": q, "search_depth": "basic", "max_results": 5}
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {settings.TAVILY_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
        emails, phones, urls = [], [], []
        for item in results:
            c = extract_contacts(f"{item.get('title','')} {item.get('content','')}")
            for e in c["emails"]:
                if e not in emails: emails.append(e)
            for p in c["phones"]:
                if p not in phones: phones.append(p)
            if c["emails"] or c["phones"]:
                urls.append(item.get("url"))
        return {"emails": emails[:3], "phones": phones[:3], "evidence_urls": [u for u in urls if u][:5]}
    except Exception:
        return {"emails": [], "phones": [], "evidence_urls": []}


async def apollo_enrich(person_name: str | None, email: str | None, company_domain: str | None) -> dict:
    if not settings.APOLLO_API_KEY or not (person_name or email):
        return {"matched": False}
    params = {"reveal_personal_emails": "false", "reveal_phone_number": "false"}
    if email:
        params["email"] = email
    if person_name:
        params["name"] = person_name
    if company_domain:
        params["domain"] = company_domain
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={"X-Api-Key": settings.APOLLO_API_KEY, "Content-Type": "application/json", "Cache-Control": "no-cache"},
                params=params,
            )
            if r.status_code >= 400:
                return {"matched": False, "error": f"Apollo {r.status_code}"}
            person = (r.json() or {}).get("person") or {}
        phones = []
        for p in person.get("phone_numbers") or []:
            n = p.get("sanitized_number") or p.get("raw_number")
            if n and n not in phones:
                phones.append(n)
        return {
            "matched": bool(person),
            "person_name": person.get("name"),
            "email": person.get("email"),
            "email_status": person.get("email_status"),
            "phone": phones[0] if phones else None,
            "linkedin_url": person.get("linkedin_url"),
            "title": person.get("title"),
            "organization": (person.get("organization") or {}).get("name") if isinstance(person.get("organization"), dict) else None,
        }
    except Exception as exc:
        return {"matched": False, "error": str(exc)[:200]}


async def enrich_candidate(title: str, text: str, url: str, ai: dict) -> dict:
    direct = extract_contacts(text)
    page = await fetch_public_page_contacts(url)
    emails = direct["emails"] + [e for e in page["emails"] if e not in direct["emails"]]
    phones = direct["phones"] + [p for p in page["phones"] if p not in direct["phones"]]
    evidence = [url] if (direct["emails"] or direct["phones"]) else []
    if page.get("source") and page["source"] not in evidence:
        evidence.append(page["source"])

    lookup = await tavily_contact_lookup(ai.get("person_name"), ai.get("company"), url)
    for e in lookup["emails"]:
        if e not in emails: emails.append(e)
    for p in lookup["phones"]:
        if p not in phones: phones.append(p)
    evidence.extend([u for u in lookup["evidence_urls"] if u not in evidence])

    company_domain = domain(url)
    apollo = await apollo_enrich(ai.get("person_name"), emails[0] if emails else None, company_domain if company_domain not in SOCIAL_DOMAINS else None)
    if apollo.get("email") and apollo["email"] not in emails:
        emails.insert(0, apollo["email"])
    if apollo.get("phone") and apollo["phone"] not in phones:
        phones.insert(0, apollo["phone"])

    status = "NOT_FOUND"
    if phones or emails:
        status = "VERIFIED_PROVIDER" if apollo.get("matched") else "PUBLIC_FOUND"
    elif ai.get("person_name"):
        status = "IDENTIFIED_NO_CONTACT"

    return {
        "phone": phones[0] if phones else None,
        "email": emails[0] if emails else None,
        "contact_status": status,
        "contact_evidence_urls": evidence[:5],
        "apollo": apollo,
    }


def build_intelligence_payload(title: str, url: str, ai: dict, score: dict, enrichment: dict) -> dict:
    total = score["total"]
    if total >= 90:
        band = "PRIORITY_BUYER"
    elif total >= 80:
        band = "HOT_BUYER"
    elif total >= 70:
        band = "QUALIFIED_BUYER"
    elif total >= 50:
        band = "QUALIFICATION_PENDING"
    else:
        band = "REJECT"
    if ai.get("classification") not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        band = "REJECT"

    missing = []
    for key, label in [("budget_hint", "Budget"), ("timeline_hint", "Timeline"), ("purpose", "Purpose"), ("authority", "Decision authority")]:
        if not ai.get(key) and not score.get(key):
            missing.append(label)
    if not enrichment.get("phone") and not enrichment.get("email"):
        missing.append("Contact details")

    return {
        "v": 1,
        "classification": ai.get("classification"),
        "band": band,
        "ai_confidence": ai.get("confidence"),
        "ai_reason": ai.get("reason"),
        "score_breakdown": {k: score[k] for k in ["purchase_intent", "budget", "location_fit", "timeline", "need", "authority", "contactability", "total"]},
        "purpose": ai.get("purpose") or score.get("purpose"),
        "authority": ai.get("authority") or score.get("authority_hint"),
        "contact_status": enrichment.get("contact_status"),
        "contact_evidence_urls": enrichment.get("contact_evidence_urls", []),
        "linkedin_url": (enrichment.get("apollo") or {}).get("linkedin_url"),
        "missing_qualification": missing,
        "source_title": title[:500],
        "source_url": url,
    }


def dump_intelligence_notes(payload: dict, extra: str | None = None) -> str:
    raw = "INTEL_JSON:" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if extra:
        raw += "\n" + extra[:800]
    return raw[:3900]


def parse_intelligence_notes(notes: str | None) -> dict:
    if not notes or not notes.startswith("INTEL_JSON:"):
        return {}
    first = notes.split("\n", 1)[0][len("INTEL_JSON:"):]
    try:
        return json.loads(first)
    except Exception:
        return {}
