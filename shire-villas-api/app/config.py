import os


class Settings:
    """
    Central config. Every value has a safe local default so the app
    boots with ZERO env vars set (SQLite, no AI key). On Railway you
    just add DATABASE_URL (auto-injected if you attach Postgres) and
    optionally GROQ_API_KEY.
    """

    PROJECT_NAME: str = "Shire Villas Lead Engine"
    ENV: str = os.getenv("ENV", "development")

    # Railway injects DATABASE_URL automatically when you attach a
    # Postgres plugin. Locally it falls back to a SQLite file so you
    # can run this with no setup at all.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./shire_villas.db")

    # Railway's Postgres URLs sometimes start with postgres:// which
    # SQLAlchemy 2.x rejects — normalize it.
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me")

    # Comma-separated list, e.g. "https://yourname.github.io,https://shire.com"
    CORS_ORIGINS: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")
    ]

    PORT: int = int(os.getenv("PORT", "8000"))


settings = Settings()
