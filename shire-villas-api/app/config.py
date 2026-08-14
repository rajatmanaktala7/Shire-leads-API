import os
import re
from dataclasses import dataclass


def _clean(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = _clean(name)
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    raw = _clean(name)
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _clean(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _safe_url(raw: str, default: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return default
    # Railway reference variables can accidentally resolve to blank; never crash boot.
    return raw


@dataclass(frozen=True)
class ConfigIssue:
    level: str
    key: str
    message: str


class Settings:
    PROJECT_NAME = "Shire Villas Buyer Intelligence OS"
    VERSION = "7.0.1"
    ENV = _clean("ENV", "production")

    DATABASE_URL = _safe_url(_clean("DATABASE_URL"), "sqlite:///./shire_villas.db")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    PORT = _env_int("PORT", 8000, 1, 65535)

    TEAM_API_KEY = _clean("TEAM_API_KEY")
    SECRET_KEY = _clean("SECRET_KEY")
    CORS_ORIGINS = [x.strip() for x in _clean("CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()]

    GROQ_API_KEY = _clean("GROQ_API_KEY")
    GROQ_MODEL = _clean("GROQ_MODEL", "llama-3.3-70b-versatile")

    TAVILY_API_KEY = _clean("TAVILY_API_KEY")
    BRAVE_SEARCH_API_KEY = _clean("BRAVE_SEARCH_API_KEY")
    LEAD_BOT_PROVIDER = _clean("LEAD_BOT_PROVIDER", "auto").lower()

    APOLLO_API_KEY = _clean("APOLLO_API_KEY")

    LEAD_BOT_MIN_SCORE = _env_float("LEAD_BOT_MIN_SCORE", 70, 0, 100)
    LEAD_BOT_MAX_RESULTS_PER_QUERY = _env_int("LEAD_BOT_MAX_RESULTS_PER_QUERY", 8, 1, 20)
    LEAD_BOT_TIME_RANGE = _clean("LEAD_BOT_TIME_RANGE", "year")
    LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER = _env_bool("LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER", True)
    LEAD_BOT_ACTIONABLE_SCORE = _env_float("LEAD_BOT_ACTIONABLE_SCORE", 70, 0, 100)
    LEAD_BOT_MIN_ADMISSION_SCORE = _env_float("LEAD_BOT_MIN_ADMISSION_SCORE", 50, 0, 100)
    AUTO_PROMOTE_QUALIFIED_LEADS = _env_bool("AUTO_PROMOTE_QUALIFIED_LEADS", False)

    FLOWCONNECT_WEBHOOK_URL = _clean("FLOWCONNECT_WEBHOOK_URL")
    FLOWCONNECT_API_KEY = _clean("FLOWCONNECT_API_KEY")
    FLOWCONNECT_WEBHOOK_SECRET = _clean("FLOWCONNECT_WEBHOOK_SECRET")

    CLOUDINARY_CLOUD_NAME = _clean("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = _clean("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = _clean("CLOUDINARY_API_SECRET")

    META_PIXEL_ID = _clean("META_PIXEL_ID")

    # Long-lived business policy: tune in Railway without code changes.
    SHIRE_MIN_BUDGET_CR = _env_float("SHIRE_MIN_BUDGET_CR", 10, 1, 100)
    SHIRE_PRIORITY_SCORE = _env_float("SHIRE_PRIORITY_SCORE", 90, 0, 100)
    SHIRE_QUALIFIED_SCORE = _env_float("SHIRE_QUALIFIED_SCORE", 70, 0, 100)
    SHIRE_TARGET_LOCATIONS = [
        x.strip().lower()
        for x in _clean("SHIRE_TARGET_LOCATIONS", "Siolim,Assagao,Vagator,Morjim,Anjuna,North Goa").split(",")
        if x.strip()
    ]

    # Run safety.
    DAILY_SUITE_LOCK_MINUTES = _env_int("DAILY_SUITE_LOCK_MINUTES", 45, 5, 180)
    HTTP_TIMEOUT_SECONDS = _env_int("HTTP_TIMEOUT_SECONDS", 30, 5, 120)

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    def config_issues(self) -> list[ConfigIssue]:
        issues: list[ConfigIssue] = []

        if not self.TEAM_API_KEY:
            issues.append(ConfigIssue("ERROR" if self.is_production else "WARN", "TEAM_API_KEY", "Team authentication is not configured."))
        if not self.SECRET_KEY:
            issues.append(ConfigIssue("ERROR" if self.is_production else "WARN", "SECRET_KEY", "Signed session secret is not configured."))
        if "*" in self.CORS_ORIGINS and self.is_production:
            issues.append(ConfigIssue("ERROR", "CORS_ORIGINS", "Wildcard CORS is forbidden in production."))

        if not (self.TAVILY_API_KEY or self.BRAVE_SEARCH_API_KEY):
            issues.append(ConfigIssue("WARN", "WEB_SEARCH", "No web-search provider is configured; discovery bots will be disabled."))
        if not self.GROQ_API_KEY:
            issues.append(ConfigIssue("WARN", "GROQ_API_KEY", "AI classifier is unavailable; conservative rule fallback will be used."))
        if not self.APOLLO_API_KEY:
            issues.append(ConfigIssue("WARN", "APOLLO_API_KEY", "Apollo is optional; contact attribution will rely on public evidence only."))
        if not self.FLOWCONNECT_WEBHOOK_URL:
            issues.append(ConfigIssue("WARN", "FLOWCONNECT_WEBHOOK_URL", "Flowconnect sync is disabled until configured."))

        if self.LEAD_BOT_MIN_ADMISSION_SCORE > self.LEAD_BOT_ACTIONABLE_SCORE:
            issues.append(ConfigIssue("WARN", "LEAD_BOT_MIN_ADMISSION_SCORE", "Admission score is above actionable score."))

        return issues

    def validate(self) -> None:
        fatal = [x for x in self.config_issues() if x.level == "ERROR"]
        if fatal:
            raise RuntimeError("; ".join(f"{x.key}: {x.message}" for x in fatal))


settings = Settings()
