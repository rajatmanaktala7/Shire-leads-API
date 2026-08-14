from app.services.lead_intelligence_service import classify_rule_based, deterministic_score

CASES = [
    ("Buyer", "I am looking to buy a 4 BHK villa in Siolim. My budget is 12 crore and I want to buy within 3 months for a second home.", "https://reddit.com/x", "REAL_BUYER"),
    ("News", "Why NRIs are investing in Goa villas: market trends and appreciation report", "https://timesofindia.indiatimes.com/x", "NEWS"),
    ("Listing", "Luxury villas for sale in Siolim Goa. Browse properties and developer offers.", "https://magicbricks.com/x", "PROPERTY_LISTING"),
]
for title, text, url, expected in CASES:
    cls = classify_rule_based(title, text, url)
    assert cls == expected, (title, cls, expected)
    score = deterministic_score(text, cls)
    if expected not in {"REAL_BUYER", "POSSIBLE_BUYER"}:
        assert score["total"] <= 49, score
print("V6 SELF TEST PASS")
