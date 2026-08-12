import re
from app.models.lead import OrganicOpportunity


def score_opportunity(text: str, location: str | None = None, budget: str | None = None, timeline: str | None = None) -> float:
    blob = " ".join([text or "", location or "", budget or "", timeline or ""]).lower()
    score = 5.0

    purchase_terms = ["looking to buy", "want to buy", "buy villa", "buy property", "second home", "investment", "purchase", "buyer"]
    goa_terms = ["goa", "north goa", "siolim", "assagao", "anjuna", "vagator", "morjim"]
    villa_terms = ["villa", "luxury home", "4bhk", "second home"]
    urgency_terms = ["immediate", "this month", "0-3", "3 months", "soon", "ready"]

    if any(x in blob for x in purchase_terms): score += 30
    if any(x in blob for x in goa_terms): score += 22
    if any(x in blob for x in villa_terms): score += 15
    if any(x in blob for x in urgency_terms): score += 13

    crore = re.search(r"(?:₹|rs\.?|inr)?\s*(\d+(?:\.\d+)?)\s*(?:cr|crore)", blob)
    if crore:
        value = float(crore.group(1))
        score += 15 if value >= 10 else 8 if value >= 7 else 3
    elif any(x in blob for x in ["10-15", "15-20", "20+"]):
        score += 15

    return round(min(score, 100), 1)


def suggested_response(o: OrganicOpportunity) -> str:
    name = o.person_name or "there"
    place = o.location or "North Goa"
    return (
        f"Hi {name}, I noticed your requirement around {place}. "
        "We work with Shire Villas in Siolim and may have something relevant. "
        "If you are still exploring, I can share the project details and current availability for you to review."
    )
