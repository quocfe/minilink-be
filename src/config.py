import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App settings
    app_name: str = "MiniLink"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database settings
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://minilink:password@localhost:5432/minilink_db"
    )

    # Redis settings
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Kafka settings
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_click_topic: str = "url_clicks"

    # Security settings
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 7
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "1044283161622-mt1fsm9lm2lmnkfj17d2p1ef5rk6ubag.apps.googleusercontent.com")

    # CORS settings
    # Comma-separated list of allowed origins, e.g. "http://localhost:5173,https://app.example.com"
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000")

    # Cookie settings
    # Secure=True bắt buộc HTTPS — tự động bật khi debug=False (production).
    # Override bằng env var COOKIE_SECURE=true|false nếu cần.
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false" if os.getenv("DEBUG", "false").lower() == "true" else "true").lower() == "true"
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax")  # "lax" | "strict" | "none"

    # URL settings
    base_url: str = os.getenv("BASE_URL", "http://localhost:8000")
    short_url_length: int = 6

    # Email / SMTP settings
    mail_username: str = os.getenv("MAIL_USERNAME", "")
    mail_password: str = os.getenv("MAIL_PASSWORD", "")
    mail_from: str = os.getenv("MAIL_FROM", "noreply@minilink.io")
    mail_from_name: str = os.getenv("MAIL_FROM_NAME", "MiniLink")
    mail_port: int = int(os.getenv("MAIL_PORT", "587"))
    mail_server: str = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    # STARTTLS=True + SSL_TLS=False  → dùng port 587 (Gmail, Outlook…)
    # STARTTLS=False + SSL_TLS=True  → dùng port 465 (SSL thuần)
    mail_starttls: bool = os.getenv("MAIL_STARTTLS", "true").lower() == "true"
    mail_ssl_tls: bool = os.getenv("MAIL_SSL_TLS", "false").lower() == "true"

    class Config:
        env_file = ".env"


settings = Settings()

