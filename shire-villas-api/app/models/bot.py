import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, Text

from app.database import Base


def gen_id() -> str:
    return str(uuid.uuid4())


def utcnow():
    return datetime.now(timezone.utc)


class LeadBotRun(Base):
    __tablename__ = "lead_bot_runs"

    id = Column(String, primary_key=True, default=gen_id)
    bot_name = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=True)
    status = Column(String, nullable=False, default="RUNNING")
    queries_run = Column(Integer, default=0)
    results_seen = Column(Integer, default=0)
    opportunities_created = Column(Integer, default=0)
    partners_created = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    low_quality_skipped = Column(Integer, default=0)
    error_text = Column(Text, nullable=True)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
