from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:admin@localhost:5432/accuradb"
    SECRET_KEY: str = "super-secret-key-change-in-production"

    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    SESSION_COOKIE_NAME: str = "accura_session"
    CSRF_COOKIE_NAME: str = "accura_csrf"
    SESSION_TTL_DAYS: int = 7
    SESSION_COOKIE_SECURE: bool = False  # set True behind HTTPS

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_MINUTES: int = 15

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()