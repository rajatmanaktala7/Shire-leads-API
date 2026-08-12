import os


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

    PORT: int = int(os.getenv("PORT", "8000"))

    # Flowconnect is the final CRM/system of record. Configure an incoming
    # webhook or API endpoint supplied by your Flowconnect account/workflow.
    FLOWCONNECT_WEBHOOK_URL: str = os.getenv("FLOWCONNECT_WEBHOOK_URL", "")
    FLOWCONNECT_API_KEY: str = os.getenv("FLOWCONNECT_API_KEY", "")
    FLOWCONNECT_WEBHOOK_SECRET: str = os.getenv("FLOWCONNECT_WEBHOOK_SECRET", "")

    # Railway persistent volume is recommended at /data for uploaded campaign media.
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "/data/uploads")

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
