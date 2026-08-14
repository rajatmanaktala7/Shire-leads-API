from app.config import settings
from app.services.lead_intelligence_service import deterministic_score, build_intelligence_payload

def main():
    assert settings.VERSION == "7.1.1"
    ai = {
        "classification": "REAL_BUYER", "person_name": "Amit Sharma",
        "buyer_intent": True, "confidence": 95, "reason": "test",
        "budget_hint": "12 Cr", "timeline_hint": "0-3 months",
        "purpose": "Second Home", "authority": "Likely principal", "location": "Siolim"
    }
    score = deterministic_score(
        "I am looking to buy a villa in Siolim. My budget is 12 Cr within 3 months. second home.",
        "REAL_BUYER", None, None
    )
    no_contact = {
        "phone": None, "email": None, "contact_status": "IDENTIFIED_NO_CONTACT",
        "contact_evidence_urls": [], "apollo": {"matched": False}, "contact_attributable": False
    }
    intel = build_intelligence_payload("Amit buyer", "https://example.com", ai, score, no_contact)
    assert intel["band"] == "CONTACT_ENRICHMENT_REQUIRED"
    assert intel["crm_ready"] is False

    with_contact = {
        "phone": "+919999999999", "email": "amit@example.com",
        "contact_status": "VERIFIED_PROVIDER", "contact_evidence_urls": [],
        "apollo": {"matched": True, "person_name": "Amit Sharma"}, "contact_attributable": True
    }
    intel2 = build_intelligence_payload("Amit buyer", "https://example.com", ai, score, with_contact)
    assert intel2["contact_attributable"] is True
    print("SHIRE V7.1 FINAL EXECUTION LAYER: PASS")

if __name__ == "__main__":
    main()
