"""
Run this once after deploying to populate the dashboard with demo data
so you can see the system working end-to-end before real leads arrive.

Usage:
    python seed_data.py
"""
import random
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal, init_db
from app.models.lead import Lead, Activity, LeadTemperature, LeadStatus

NAMES = [
    ("Arjun Mehta", "arjun.mehta@example.com", "+91 98765 43210", "Mehta Group"),
    ("Priya Sharma", "priya.sharma@example.com", "+91 98123 45678", None),
    ("Rohan Kapoor", "rohan.kapoor@example.com", "+44 7911 123456", "Kapoor Ventures"),
    ("Ananya Iyer", "ananya.iyer@example.com", "+91 99887 76655", None),
    ("Vikram Singh", "vikram.singh@example.com", "+971 50 123 4567", "Singh Holdings"),
    ("Neha Patel", "neha.patel@example.com", "+1 415 555 0192", None),
    ("Karan Malhotra", "karan.malhotra@example.com", "+91 98456 12378", "Malhotra & Co"),
    ("Simran Kaur", "simran.kaur@example.com", "+65 8123 4567", None),
    ("Aditya Rao", "aditya.rao@example.com", "+91 97654 32109", "Rao Industries"),
    ("Ishita Bose", "ishita.bose@example.com", "+91 96543 21098", None),
]

SOURCES = ["website", "whatsapp", "referral", "instagram_ad", "linkedin"]
ACTION_SEQUENCE = [
    "PAGE_VISIT", "FORM_STARTED", "BOT_INITIALIZED", "CONVERSATION_STARTED",
    "USER_RESPONSE", "AI_RESPONSE", "QUALIFICATION_COMPLETE",
]


def seed():
    init_db()
    db = SessionLocal()

    if db.query(Lead).count() > 0:
        print("Leads already exist. Skipping seed (delete shire_villas.db to reset).")
        db.close()
        return

    for name, email, phone, company in NAMES:
        budget = random.uniform(20, 100)
        authority = random.uniform(20, 100)
        need = random.uniform(20, 100)
        timeline = random.uniform(20, 100)
        fit = random.uniform(40, 100)
        overall = round(budget * 0.3 + timeline * 0.2 + authority * 0.2 + need * 0.15 + fit * 0.15, 1)

        if overall >= 75:
            temp = LeadTemperature.HOT
        elif overall >= 50:
            temp = LeadTemperature.WARM
        else:
            temp = LeadTemperature.COLD

        status = random.choice(list(LeadStatus))
        created = datetime.now(timezone.utc) - timedelta(days=random.randint(0, 14))

        lead = Lead(
            name=name, email=email, phone=phone, company=company,
            source=random.choice(SOURCES),
            budget_score=round(budget, 1), authority_score=round(authority, 1),
            need_score=round(need, 1), timeline_score=round(timeline, 1),
            fit_score=round(fit, 1), overall_score=overall,
            temperature=temp, status=status,
            budget_range=random.choice(["10-15 Cr", "15-20 Cr", "20+ Cr"]),
            timeline=random.choice(["0-3 months", "3-6 months", "6-12 months"]),
            deal_value_estimate=round(random.uniform(10, 25), 2) * 10_000_000,
            created_at=created, updated_at=created,
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

        for i, action in enumerate(ACTION_SEQUENCE):
            db.add(Activity(
                lead_id=lead.id,
                action_type=action,
                description=f"{action.replace('_', ' ').title()} for {name}",
                created_at=created + timedelta(minutes=i * 3),
            ))
        db.commit()

    print(f"Seeded {len(NAMES)} leads with activity history.")
    db.close()


if __name__ == "__main__":
    seed()
