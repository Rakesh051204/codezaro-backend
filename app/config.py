from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./codezaro.db"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Anthropic (optional – we now use Groq)
    ANTHROPIC_API_KEY: str = ""

    # Groq (free tier)
    GROQ_API_KEY: str = ""

    # Tier limits
    FREE_MONTHLY_LIMIT: int = 20
    PRO_MONTHLY_LIMIT: int = 9999
    TEAM_MONTHLY_LIMIT: int = 99999

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()