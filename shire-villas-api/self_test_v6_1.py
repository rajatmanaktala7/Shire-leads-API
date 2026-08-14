from app.services.lead_intelligence_service import (
    classify_rule_based,
    deterministic_score,
    build_intelligence_payload,
)

def main():
    # Company website contact must never become a real buyer by itself.
    text = "Luxury villas in Goa. Contact +91 9044089911 for details."
    cls = classify_rule_based("Property company", text, "https://example.com")
    score = deterministic_score(text, cls, "+919044089911", None)
    ai = {
        "classification": cls,
        "person_name": None,
        "buyer_intent": False,
        "confidence": 60,
        "reason": "test",
        "budget_hint": None,
        "timeline_hint": None,
        "purpose": None,
        "authority": None,
        "location": "Goa",
    }
    enrichment = {
        "phone": None,
        "email": None,
        "contact_status": "IDENTITY_REQUIRED",
        "contact_evidence_urls": [],
        "contact_attributable": False,
        "apollo": {"matched": False},
    }
    intel = build_intelligence_payload("Property company", "https://example.com", ai, score, enrichment)
    assert intel["crm_ready"] is False
    assert intel["band"] in {"REJECT", "IDENTITY_REQUIRED"}

    # Named buyer + provider-attributed contact + >=10 Cr can be CRM-ready.
    buyer_text = "I am looking to buy a villa in Siolim. My budget is 12 Cr. I want a second home within 3 months."
    score2 = deterministic_score(buyer_text, "REAL_BUYER", "+919999999999", "amit@example.com")
    ai2 = {
        "classification": "REAL_BUYER",
        "person_name": "Amit Sharma",
        "buyer_intent": True,
        "confidence": 95,
        "reason": "Explicit first-person purchase intent",
        "budget_hint": "12 Cr",
        "timeline_hint": "0-3 months",
        "purpose": "Second Home",
        "authority": "Likely principal",
        "location": "Siolim",
    }
    enrichment2 = {
        "phone": "+919999999999",
        "email": "amit@example.com",
        "contact_status": "VERIFIED_PROVIDER",
        "contact_evidence_urls": ["https://example.com/amit"],
        "contact_attributable": True,
        "apollo": {"matched": True, "person_name": "Amit Sharma"},
    }
    intel2 = build_intelligence_payload("Amit buying Goa villa", "https://example.com/amit", ai2, score2, enrichment2)
    assert intel2["person_identity_verified"] is True
    assert intel2["contact_attributable"] is True
    assert intel2["shire_budget_fit"] is True
    assert intel2["crm_ready"] is True
    print("V6.1 BUYER IDENTITY GATE: PASS")

if __name__ == "__main__":
    main()
