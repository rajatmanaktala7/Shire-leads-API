import os
import sys

from app.config import settings
from app.services.lead_intelligence_service import (
    _looks_like_named_person,
    _same_person_name,
    deterministic_score,
    build_intelligence_payload,
)


def assert_true(x, msg):
    if not x:
        raise AssertionError(msg)


def main():
    assert_true(settings.VERSION == "7.1.1", "Wrong version")
    assert_true(_looks_like_named_person("Amit Sharma"), "Human identity rejected")
    assert_true(not _looks_like_named_person("Identity pending"), "Placeholder identity accepted")
    assert_true(not _looks_like_named_person("Property Kumbh"), "Business identity accepted")
    assert_true(_same_person_name("A. Sharma", "Amit Sharma"), "Identity matching failed")

    # False lead must never be CRM ready.
    score = deterministic_score("Luxury villas for sale in Goa. Contact us today.", "UNKNOWN")
    ai = {
        "classification": "UNKNOWN",
        "person_name": None,
        "buyer_intent": False,
        "confidence": 90,
        "reason": "Business content",
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
        "apollo": {"matched": False},
        "contact_attributable": False,
    }
    intel = build_intelligence_payload("Company page", "https://example.com", ai, score, enrichment)
    assert_true(not intel["crm_ready"], "False business lead became CRM ready")

    # Real, named, attributed, budget-fit buyer may pass.
    text = "I am looking to buy a villa in Siolim. My budget is 12 Cr. I want a second home within 3 months."
    score2 = deterministic_score(text, "REAL_BUYER", "+919999999999", "amit@example.com")
    ai2 = {
        "classification": "REAL_BUYER",
        "person_name": "Amit Sharma",
        "buyer_intent": True,
        "confidence": 97,
        "reason": "Explicit first-person purchase intent",
        "identity_evidence": "Named author",
        "intent_evidence": "Looking to buy",
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
        "apollo": {"matched": True, "person_name": "Amit Sharma"},
        "contact_attributable": True,
    }
    intel2 = build_intelligence_payload("Amit", "https://example.com/amit", ai2, score2, enrichment2)
    assert_true(intel2["crm_ready"], "Qualified buyer failed CRM gate")

    print("SHIRE V7 STABLE CORE: ALL TESTS PASS")


if __name__ == "__main__":
    main()
