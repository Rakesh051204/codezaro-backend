from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite:///./codezaro.db"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Anthropic (optional)
    ANTHROPIC_API_KEY: str = ""

    # Groq
    GROQ_API_KEY: str = ""

    # Stripe
    STRIPE_PUBLISHABLE_KEY: str = "pk_test_51TlQob4cGrYPt8vrBWNUWJClvrB1t8ZxQ6XFBJ4sbu7i3b1c1HhH7H3hdK8ktQLVGOlNXsUnF8HsS7kjchdSnJKo00mEHAhK2R"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = "whsec_hxHTLuHJ7594ehRotnHlQ52oAqV3CpWK"

    # Tier limits
    FREE_MONTHLY_LIMIT: int = 20
    PRO_MONTHLY_LIMIT: int = 9999
    TEAM_MONTHLY_LIMIT: int = 99999

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()