"""Central configuration (12-factor: everything comes from environment variables)."""
import os

ENV = os.getenv("ENV", "development")            # development | production
IS_PROD = ENV == "production"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./trialmatch.db")
REDIS_URL = os.getenv("REDIS_URL", "")            # empty -> in-process TTL cache
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_TTL_MIN = int(os.getenv("JWT_TTL_MIN", "60"))
DATA_KEY = os.getenv("DATA_KEY", "")              # Fernet key (urlsafe base64, 32 bytes)
CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "").split(",") if o]
CACHE_TTL = int(os.getenv("CACHE_TTL", "600"))
LLM_ENABLED = os.getenv("LLM_ENABLED", "0") == "1"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
LOGIN_RATE_PER_MIN = int(os.getenv("LOGIN_RATE_PER_MIN", "10"))

if IS_PROD and (not JWT_SECRET or not DATA_KEY):
    raise RuntimeError("JWT_SECRET and DATA_KEY must be set when ENV=production")
if not JWT_SECRET:
    JWT_SECRET = "dev-only-secret-change-me-dev-only-secret"
