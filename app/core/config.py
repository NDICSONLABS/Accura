from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://postgres:admin@localhost:5432/accuradb"
    SECRET_KEY: str = "super-secret-key-change-in-production"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()