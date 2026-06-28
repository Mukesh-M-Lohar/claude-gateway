import os
from pathlib import Path
from pydantic_settings import BaseSettings

# Define base directory
BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # Server Settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    
    # API Keys
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # Google AI key
    
    # Cache Backend Options: "sqlite", "redis", "memory"
    EXACT_CACHE_BACKEND: str = "sqlite"
    SEMANTIC_CACHE_BACKEND: str = "sqlite"
    
    # Embedding Provider Options: "openai", "gemini", "mock"
    EMBEDDING_PROVIDER: str = "mock"
    
    # SQLite Configuration
    SQLITE_DB_PATH: str = str(BASE_DIR / "gateway.db")
    
    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    
    # Qdrant Configuration
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "claude_gateway_cache"
    
    # Semantic Search Settings
    SIMILARITY_THRESHOLD: float = 0.95
    EMBEDDING_DIMENSION: int = 1536  # Default for text-embedding-3-small or text-embedding-ada-002
    
    # Git Watcher Settings
    GIT_WATCHER_INTERVAL: int = 30  # seconds
    
    # Claude Model Pricing (per 1,000,000 tokens)
    # Pricing sourced from Anthropic's pricing pages
    MODEL_PRICING: dict = {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet-20240620": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
        "claude-3-5-haiku": {"input": 0.80, "output": 4.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
        "default": {"input": 3.00, "output": 15.00}  # Fallback
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

# Instantiate settings
settings = Settings()

# Auto-detect embedding provider if keys are set and provider is default mock
if settings.EMBEDDING_PROVIDER == "mock":
    if settings.OPENAI_API_KEY:
        settings.EMBEDDING_PROVIDER = "openai"
    elif settings.GEMINI_API_KEY:
        settings.EMBEDDING_PROVIDER = "gemini"
