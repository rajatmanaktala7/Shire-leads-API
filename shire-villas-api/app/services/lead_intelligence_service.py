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


def _budget_top_crore(budget_hint: str | None) -> float | None:
    if not budget_hint:
        return None
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", budget_hint)]
    return max(nums) if nums else None


def _looks_like_named_person(name: str | None) -> bool:
    if not name:
        return False
    n = re.sub(r"\s+", " ", str(name)).strip()
    if len(n) < 4 or len(n) > 80:
        return False
    bad = {
        "identity pending", "web opportunity", "admin", "sales", "team",
        "contact", "support", "info", "property", "properties", "realty",
        "estate", "developer", "broker", "company",
    }
    low = n.lower()
    if low in bad or any(low.startswith(x + " ") for x in bad):
        return False
    parts = [p for p in re.split(r"\s+", n) if p]
    return 1 <= len(parts) <= 5 and any(ch.isalpha() for ch in n)


def _same_person_name(a: str | None, b: str | None) -> bool:
    """
    Conservative identity comparison that accepts common initials such as
    "A. Sharma" == "Amit Sharma" while still requiring surname agreement.
    """
    if not _looks_like_named_person(a) or not _looks_like_named_person(b):
        return False

    def parts(value: str) -> list[str]:
        cleaned = re.sub(r"[^a-z ]", " ", value.lower())
        return [x for x in cleaned.split() if x]

    pa = parts(a)
    pb = parts(b)
    if not pa or not pb:
        return False

    if pa == pb:
        return True

    # Require matching surname for non-exact matches.
    if pa[-1] != pb[-1]:
        return False

    # First names may be full-name/full-name or initial/full-name.
    fa, fb = pa[0], pb[0]
    if fa == fb:
        return True
    if len(fa) == 1 and fb.startswith(fa):
        return True
    if len(fb) == 1 and fa.startswith(fb):
        return True
    return False


def _result_mentions_person(item: dict, person_name: str) -> bool:
    blob = f"{item.get('title','')} {item.get('content','')} {item.get('raw_content','') or ''}".lower()
    tokens = [x for x in re.sub(r"[^a-z ]", " ", person_name.lower()).split() if len(x) > 1]
    if len(tokens) >= 2:
        return tokens[0] in blob and tokens[-1] in blob
    return bool(tokens and tokens[0] in blob)

def _email_is_generic(email: str | None) -> bool:
    if not email or "@" not in email:
        return True
    local = email.split("@", 1)[0].lower()
    generic = (
        "info", "sales", "contact", "hello", "admin", "support", "office",
        "team", "enquiry", "enquiries", "marketing", "groupmail", "care",
    )
    return local in generic or any(local.startswith(x + ".") or local.startswith(x + "_") for x in generic)


def _contact_is_attributable(person_name: str | None, email: str | None, phone: str | None, apollo: dict | None) -> bool:
    if not _looks_like_named_person(person_name):
        return False
    apollo = apollo or {}
    if apollo.get("matched"):
        apollo_name = (apollo.get("person_name") or "").strip().lower()
        wanted = (person_name or "").strip().lower()
        if apollo_name and (apollo_name == wanted or wanted in apollo_name or apollo_name in wanted):
            return bool(apollo.get("email") or apollo.get("phone"))
    if email and not _email_is_generic(email):
        # Public email may be useful, but without provider identity it is not verified.
        return True
    # A bare phone scraped from a page is not attributable to the named buyer by itself.
    return False

def deterministic_score(text: str, classification: str, phone: str | None = None, email: str | None = None) -> dict:
    b = (text or "").lower()

    if any(x in b for x in FIRST_PERSON) and any(x in b for x in BUYING_PHRASES):
        intent = 25
    elif any(x in b for x in ["looking to buy", "want to buy", "need a villa", "planning to buy"]):
        intent = 20
    elif any(x in b for x in BUYING_PHRASES):
        intent = 10
    else:
        intent = 0

    budget_hint = infer_budget(b)
    budget_top = _budget_top_crore(budget_hint)
    if budget_top is None:
        budget = 0
    elif budget_top >= 10:
        budget = 20
    elif budget_top >= 8:
        budget = 10
    else:
        budget = 0

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

    timeline_hint = infer_timeline(b)
    timeline = {"0-3 months": 15, "3-6 months": 12, "6-12 months": 9, "Exploring": 2, None: 0}[timeline_hint]

    purpose = infer_purpose(b)
    need = {"Second Home": 10, "Own Use": 10, "Relocation": 10, "Investment": 8, None: 0}[purpose]

    authority_hint = infer_authority(b)
    authority = 5 if authority_hint == "Likely principal" else 4 if authority_hint == "Joint decision" else 0

    # Contactability is deliberately conservative. Generic page contacts are not
    # proof of buyer identity. The enrichment stage may later overwrite this with
    # attributable contact status in build_intelligence_payload.
    contactability = 2 if phone and email else 1 if (phone or email) else 0

    score = intent + budget + fit + timeline + need + authority + contactability
    if classification not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        score = min(score, 39)

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
        "budget_top_crore": budget_top,
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
    fallback["buyer_intent"] = False  # no named human can be proven by rule-only fallback
    if not settings.GROQ_API_KEY:
        return fallback

    system = """You are Shire Villas' buyer-intelligence classifier. Shire sells ultra-luxury 4BHK villas in Siolim, North Goa, starting around INR 10 crore.

Your task is NOT topical matching. Your task is to prove an identifiable HUMAN buyer signal from public evidence.

HARD RULES:
1. A company, developer, broker, property portal, SEO page, news article, market report, generic social post, listing, or business website is NEVER a REAL_BUYER.
2. REAL_BUYER requires BOTH an identifiable person's name AND explicit evidence that this same person is personally considering, asking about, planning, or actively making a property purchase.
3. POSSIBLE_BUYER may be used only when a named person exists but purchase intent is incomplete/ambiguous.
4. If person_name is null, classification MUST NOT be REAL_BUYER or POSSIBLE_BUYER.
5. Do not treat a website's phone/email as belonging to the buyer unless evidence ties it to that named person.
6. Never invent person_name, company, budget, timeline, authority, phone, email, or location.
7. Use null when evidence is missing.

Return ONLY valid JSON with keys:
classification, person_name, company, buyer_intent, confidence, reason,
budget_hint, timeline_hint, purpose, authority, location.

classification must be one of:
REAL_BUYER,POSSIBLE_BUYER,BROKER,CHANNEL_PARTNER,DEVELOPER,PROPERTY_LISTING,
NEWS,BLOG,MARKET_REPORT,GENERIC_SOCIAL_CONTENT,UNKNOWN."""

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
        person_name = data.get("person_name") or None
        if cls in {"REAL_BUYER", "POSSIBLE_BUYER"} and not _looks_like_named_person(person_name):
            cls = "UNKNOWN"
        return {
            "classification": cls,
            "person_name": person_name,
            "company": data.get("company") or None,
            "buyer_intent": bool(data.get("buyer_intent")) and cls in {"REAL_BUYER", "POSSIBLE_BUYER"} and _looks_like_named_person(person_name),
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


async def resolve_buyer_identity(title: str, text: str, url: str, initial_ai: dict) -> dict:
    """
    Second-pass identity resolution for high-intent public signals.
    It is deliberately conservative: it may improve a named-person result,
    but it cannot create a buyer from a company/portal/article page.
    """
    if not settings.GROQ_API_KEY:
        return initial_ai

    d = domain(url)
    social_or_ugc = d in SOCIAL_DOMAINS or d.endswith("reddit.com") or d.endswith("quora.com")
    if not social_or_ugc and initial_ai.get("classification") not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        return initial_ai

    prompt = """You are resolving the identity behind a potential public buyer-intent signal for Shire Villas.

STRICT RULES:
- Extract a HUMAN name only if the supplied title/text itself supports that identity.
- Do not use a company, website, publication, property brand, broker brand, page title, or username-like business name as person_name.
- buyer_intent=true only when the SAME human is personally asking about, planning, considering, or stating a purchase.
- Mere discussion of Goa property, investing, market trends, or a property's sale is not buyer intent.
- Never invent missing identity, budget, timeline, phone, or email.
- If identity is not supported, person_name=null and buyer_intent=false.

Return ONLY JSON:
{
 "classification":"REAL_BUYER|POSSIBLE_BUYER|UNKNOWN",
 "person_name":null,
 "buyer_intent":false,
 "confidence":0,
 "reason":"",
 "identity_evidence":"",
 "intent_evidence":"",
 "budget_hint":null,
 "timeline_hint":null,
 "purpose":null,
 "authority":null,
 "location":null,
 "company":null
}"""
    payload = {
        "title": title[:1000],
        "text": text[:7000],
        "url": url,
        "initial": initial_ai,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.GROQ_MODEL,
                    "temperature": 0,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
            r.raise_for_status()
            data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:
        return initial_ai

    name = data.get("person_name")
    cls = data.get("classification") if data.get("classification") in {"REAL_BUYER", "POSSIBLE_BUYER"} else "UNKNOWN"
    buyer_intent = bool(data.get("buyer_intent"))
    if not _looks_like_named_person(name) or not buyer_intent:
        return {**initial_ai, "classification": "UNKNOWN", "person_name": None, "buyer_intent": False}

    return {
        **initial_ai,
        "classification": cls,
        "person_name": name,
        "buyer_intent": True,
        "confidence": max(float(initial_ai.get("confidence") or 0), float(data.get("confidence") or 0)),
        "reason": data.get("reason") or initial_ai.get("reason"),
        "identity_evidence": (data.get("identity_evidence") or "")[:700],
        "intent_evidence": (data.get("intent_evidence") or "")[:700],
        "budget_hint": data.get("budget_hint") or initial_ai.get("budget_hint"),
        "timeline_hint": data.get("timeline_hint") or initial_ai.get("timeline_hint"),
        "purpose": data.get("purpose") or initial_ai.get("purpose"),
        "authority": data.get("authority") or initial_ai.get("authority"),
        "location": data.get("location") or initial_ai.get("location"),
        "company": data.get("company") or initial_ai.get("company"),
    }

async def tavily_contact_lookup(person_name: str | None, company: str | None, source_url: str | None) -> dict:
    if not settings.TAVILY_API_KEY or not _looks_like_named_person(person_name):
        return {"emails": [], "phones": [], "evidence_urls": [], "identity_matches": []}

    queries = [
        f'"{person_name}" email contact',
        f'"{person_name}" phone contact',
        f'"{person_name}" LinkedIn',
    ]
    if company:
        queries.insert(0, f'"{person_name}" "{company}" email phone')

    emails, phones, urls, matches = [], [], [], []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for q in queries[:4]:
                payload = {
                    "query": q,
                    "search_depth": "advanced",
                    "chunks_per_source": 2,
                    "max_results": 5,
                    "include_raw_content": "text",
                    "exclude_domains": ["facebook.com", "instagram.com"],
                }
                r = await client.post(
                    "https://api.tavily.com/search",
                    headers={
                        "Authorization": f"Bearer {settings.TAVILY_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if r.status_code >= 400:
                    continue
                for item in r.json().get("results", []):
                    if not _result_mentions_person(item, person_name):
                        continue
                    blob = f"{item.get('title','')} {item.get('content','')} {item.get('raw_content','') or ''}"
                    c = extract_contacts(blob)
                    if not c["emails"] and not c["phones"]:
                        continue
                    for e in c["emails"]:
                        if not _email_is_generic(e) and e not in emails:
                            emails.append(e)
                    for p in c["phones"]:
                        if p not in phones:
                            phones.append(p)
                    u = item.get("url")
                    if u and u not in urls:
                        urls.append(u)
                    matches.append({
                        "url": u,
                        "title": (item.get("title") or "")[:300],
                        "mentions_person": True,
                    })
    except Exception:
        pass

    return {
        "emails": emails[:3],
        "phones": phones[:3],
        "evidence_urls": urls[:5],
        "identity_matches": matches[:8],
    }


async def apollo_enrich(person_name: str | None, email: str | None, company_domain: str | None) -> dict:
    if not settings.APOLLO_API_KEY or not _looks_like_named_person(person_name):
        return {"matched": False}

    params = {"reveal_personal_emails": "false", "reveal_phone_number": "false", "name": person_name}
    if email and not _email_is_generic(email):
        params["email"] = email
    if company_domain:
        params["domain"] = company_domain

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                "https://api.apollo.io/api/v1/people/match",
                headers={
                    "X-Api-Key": settings.APOLLO_API_KEY,
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache",
                    "accept": "application/json",
                },
                params=params,
            )
            if r.status_code >= 400:
                return {"matched": False, "error": f"Apollo {r.status_code}"}
            person = (r.json() or {}).get("person") or {}
    except Exception as exc:
        return {"matched": False, "error": str(exc)[:200]}

    returned_name = person.get("name")
    if not _same_person_name(person_name, returned_name):
        return {"matched": False, "error": "Apollo returned a different identity"}

    phones = []
    for p in person.get("phone_numbers") or []:
        n = p.get("sanitized_number") or p.get("raw_number")
        if n and n not in phones:
            phones.append(n)

    return {
        "matched": bool(person),
        "person_name": returned_name,
        "email": person.get("email"),
        "email_status": person.get("email_status"),
        "phone": phones[0] if phones else None,
        "linkedin_url": person.get("linkedin_url"),
        "title": person.get("title"),
        "organization": (person.get("organization") or {}).get("name")
            if isinstance(person.get("organization"), dict) else None,
    }


async def enrich_candidate(title: str, text: str, url: str, ai: dict) -> dict:
    person_name = ai.get("person_name")
    if not _looks_like_named_person(person_name):
        return {
            "phone": None,
            "email": None,
            "contact_status": "IDENTITY_REQUIRED",
            "contact_evidence_urls": [],
            "apollo": {"matched": False},
            "contact_attributable": False,
        }

    lookup = await tavily_contact_lookup(person_name, ai.get("company"), url)
    candidate_email = lookup["emails"][0] if lookup["emails"] else None
    candidate_phone = lookup["phones"][0] if lookup["phones"] else None

    # For a social/UGC source we usually do not know employer domain.
    company_domain = None
    if ai.get("company"):
        possible = domain(url)
        if possible and possible not in SOCIAL_DOMAINS:
            company_domain = possible

    apollo = await apollo_enrich(person_name, candidate_email, company_domain)

    if apollo.get("matched") and (apollo.get("email") or apollo.get("phone")):
        return {
            "phone": apollo.get("phone"),
            "email": apollo.get("email"),
            "contact_status": "VERIFIED_PROVIDER",
            "contact_evidence_urls": lookup.get("evidence_urls", [])[:5],
            "apollo": apollo,
            "contact_attributable": True,
        }

    # Public contact is accepted only when a search result explicitly contains
    # the same person's name AND that contact, recorded by tavily_contact_lookup.
    if lookup.get("identity_matches") and (candidate_email or candidate_phone):
        return {
            "phone": candidate_phone,
            "email": candidate_email,
            "contact_status": "ATTRIBUTED_PUBLIC",
            "contact_evidence_urls": lookup.get("evidence_urls", [])[:5],
            "apollo": apollo,
            "contact_attributable": True,
        }

    return {
        "phone": None,
        "email": None,
        "contact_status": "IDENTIFIED_NO_CONTACT",
        "contact_evidence_urls": lookup.get("evidence_urls", [])[:5],
        "apollo": apollo,
        "contact_attributable": False,
    }


def build_intelligence_payload(title: str, url: str, ai: dict, score: dict, enrichment: dict) -> dict:
    person_ok = _looks_like_named_person(ai.get("person_name") or (enrichment.get("apollo") or {}).get("person_name"))
    buyer_class = ai.get("classification") in {"REAL_BUYER", "POSSIBLE_BUYER"} and bool(ai.get("buyer_intent"))
    attributable_contact = bool(enrichment.get("contact_attributable")) and enrichment.get("contact_status") in {
        "VERIFIED_PROVIDER", "ATTRIBUTED_PUBLIC"
    }
    budget_top = score.get("budget_top_crore")
    explicit_budget_fail = budget_top is not None and budget_top < max(1.0, settings.SHIRE_MIN_BUDGET_CR - 2.0)
    shire_budget_fit = budget_top is not None and budget_top >= settings.SHIRE_MIN_BUDGET_CR

    # Recalculate the contact component only after attribution is known.
    contact_points = 10 if attributable_contact and enrichment.get("phone") and enrichment.get("email") else 9 if attributable_contact and enrichment.get("phone") else 8 if attributable_contact and enrichment.get("email") else 0
    total = (
        score.get("purchase_intent", 0)
        + score.get("budget", 0)
        + score.get("location_fit", 0)
        + score.get("timeline", 0)
        + score.get("need", 0)
        + score.get("authority", 0)
        + contact_points
    )
    total = round(min(100, total), 1)
    score["contactability"] = contact_points
    score["total"] = total

    if not buyer_class:
        band = "REJECT"
    elif not person_ok:
        band = "IDENTITY_REQUIRED"
    elif explicit_budget_fail:
        band = "REJECT"
    elif not attributable_contact:
        band = "CONTACT_ENRICHMENT_REQUIRED"
    elif not shire_budget_fit:
        band = "QUALIFICATION_PENDING"
    elif total >= settings.SHIRE_PRIORITY_SCORE:
        band = "PRIORITY_BUYER"
    elif total >= 80:
        band = "HOT_BUYER"
    elif total >= settings.SHIRE_QUALIFIED_SCORE:
        band = "QUALIFIED_BUYER"
    else:
        band = "QUALIFICATION_PENDING"

    missing = []
    if not person_ok:
        missing.append("Buyer identity")
    for key, label in [
        ("budget_hint", "Budget"),
        ("timeline_hint", "Timeline"),
        ("purpose", "Purpose"),
        ("authority", "Decision authority"),
    ]:
        if not ai.get(key) and not score.get(key):
            missing.append(label)
    if not attributable_contact:
        missing.append("Attributable buyer contact")
    if budget_top is None:
        missing.append("Budget confirmation")

    crm_ready = bool(
        person_ok
        and buyer_class
        and attributable_contact
        and shire_budget_fit
        and total >= settings.SHIRE_QUALIFIED_SCORE
        and band in {"QUALIFIED_BUYER", "HOT_BUYER", "PRIORITY_BUYER"}
    )

    return {
        "v": 2,
        "classification": ai.get("classification"),
        "band": band,
        "person_identity_verified": person_ok,
        "buyer_intent_verified": buyer_class,
        "contact_attributable": attributable_contact,
        "shire_budget_fit": shire_budget_fit,
        "budget_top_crore": budget_top,
        "crm_ready": crm_ready,
        "ai_confidence": ai.get("confidence"),
        "ai_reason": ai.get("reason"),
        "identity_evidence": ai.get("identity_evidence"),
        "intent_evidence": ai.get("intent_evidence"),
        "score_breakdown": {
            "purchase_intent": score.get("purchase_intent", 0),
            "budget": score.get("budget", 0),
            "location_fit": score.get("location_fit", 0),
            "timeline": score.get("timeline", 0),
            "need": score.get("need", 0),
            "authority": score.get("authority", 0),
            "contactability": contact_points,
            "total": total,
        },
        "purpose": ai.get("purpose") or score.get("purpose"),
        "authority": ai.get("authority") or score.get("authority_hint"),
        "contact_status": enrichment.get("contact_status"),
        "contact_evidence_urls": enrichment.get("contact_evidence_urls", []),
        "linkedin_url": (enrichment.get("apollo") or {}).get("linkedin_url"),
        "missing_qualification": list(dict.fromkeys(missing)),
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
