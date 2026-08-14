import os


def _env_int(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got: {raw!r}")


def _env_float(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be numeric, got: {raw!r}")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


class Settings:
    PROJECT_NAME: str = "Shire Villas Lead Engine"
    ENV: str = os.getenv("ENV", "development")

    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./shire_villas.db")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    META_PIXEL_ID: str = os.getenv("META_PIXEL_ID", "")

    # Required for team-only dashboard/API routes in production.
    TEAM_API_KEY: str = os.getenv("TEAM_API_KEY", "")

    # Keep for future signed sessions/tokens. Never use a predictable production default.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")

    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",")
        if o.strip()
    ]

    PORT: int = _env_int("PORT", 8000)

    # Flowconnect is the final CRM/system of record. Configure an incoming
    # webhook or API endpoint supplied by your Flowconnect account/workflow.
    FLOWCONNECT_WEBHOOK_URL: str = os.getenv("FLOWCONNECT_WEBHOOK_URL", "")
    FLOWCONNECT_API_KEY: str = os.getenv("FLOWCONNECT_API_KEY", "")
    FLOWCONNECT_WEBHOOK_SECRET: str = os.getenv("FLOWCONNECT_WEBHOOK_SECRET", "")

    # Cloudinary stores landing-page images and large videos. The API secret
    # stays server-side and is used only to sign uploads for authenticated team users.
    CLOUDINARY_CLOUD_NAME: str = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY: str = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET: str = os.getenv("CLOUDINARY_API_SECRET", "")


    # Advanced Organic Lead Bots. Tavily is the recommended search provider;
    # Brave Search can be configured as a fallback. Keys remain server-side.
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "").strip()
    BRAVE_SEARCH_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    LEAD_BOT_PROVIDER: str = os.getenv("LEAD_BOT_PROVIDER", "auto")
    LEAD_BOT_MIN_SCORE: float = _env_float("LEAD_BOT_MIN_SCORE", 70)
    LEAD_BOT_MAX_RESULTS_PER_QUERY: int = _env_int("LEAD_BOT_MAX_RESULTS_PER_QUERY", 8)
    LEAD_BOT_TIME_RANGE: str = os.getenv("LEAD_BOT_TIME_RANGE", "week")

    # V6 Buyer Intelligence settings. Apollo is optional; public-source enrichment works without it.
    APOLLO_API_KEY: str = os.getenv("APOLLO_API_KEY", "").strip()
    LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER: bool = _env_bool("LEAD_BOT_REQUIRE_IDENTIFIABLE_BUYER", True)
    LEAD_BOT_ACTIONABLE_SCORE: float = _env_float("LEAD_BOT_ACTIONABLE_SCORE", 70)
    LEAD_BOT_MIN_ADMISSION_SCORE: float = _env_float("LEAD_BOT_MIN_ADMISSION_SCORE", 50)
    AUTO_PROMOTE_QUALIFIED_LEADS: bool = _env_bool("AUTO_PROMOTE_QUALIFIED_LEADS", False)

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() == "production"

    def validate(self) -> None:
        if self.is_production:
            missing = []
            if not self.TEAM_API_KEY:
                missing.append("TEAM_API_KEY")
            if not self.SECRET_KEY:
                missing.append("SECRET_KEY")
            if "*" in self.CORS_ORIGINS:
                raise RuntimeError("CORS_ORIGINS cannot contain '*' in production.")
            if missing:
                raise RuntimeError(
                    "Missing required production environment variables: "
                    + ", ".join(missing)
                )


settings = Settings()
