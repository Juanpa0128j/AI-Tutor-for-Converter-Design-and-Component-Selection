"""Configuration management for the application."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False


@dataclass
class CatalogConfig:
    """Configuration for component catalogs."""
    
    # DigiKey
    digikey_client_id: Optional[str] = None
    digikey_client_secret: Optional[str] = None
    
    # Mouser
    mouser_api_key: Optional[str] = None
    
    # LCSC
    lcsc_api_key: Optional[str] = None
    
    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60


@dataclass
class CacheConfig:
    """Configuration for Redis cache."""
    
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_cache_ttl: int = 86400  # 24 hours


@dataclass
class RecommendationConfig:
    """Configuration for component recommendation."""
    
    default_weight_cost: float = 0.30
    default_weight_availability: float = 0.25
    default_weight_efficiency: float = 0.25
    default_weight_thermal: float = 0.20


@dataclass
class RAGConfig:
    """Configuration for RAG service."""
    
    unstructured_timeout: int = 60


@dataclass
class AppConfig:
    """Application configuration."""
    
    catalog: CatalogConfig
    cache: CacheConfig
    recommendation: RecommendationConfig
    rag: RAGConfig
    
    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> AppConfig:
        """Load configuration from environment variables."""
        if DOTENV_AVAILABLE:
            load_dotenv(env_file or ".env")
        
        catalog = CatalogConfig(
            digikey_client_id=os.getenv("DIGIKEY_CLIENT_ID"),
            digikey_client_secret=os.getenv("DIGIKEY_CLIENT_SECRET"),
            mouser_api_key=os.getenv("MOUSER_API_KEY"),
            lcsc_api_key=os.getenv("LCSC_API_KEY"),
            rate_limit_requests=int(os.getenv("CATALOG_RATE_LIMIT_REQUESTS", "100")),
            rate_limit_period=int(os.getenv("CATALOG_RATE_LIMIT_PERIOD", "60")),
        )
        
        cache = CacheConfig(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            redis_password=os.getenv("REDIS_PASSWORD"),
            redis_cache_ttl=int(os.getenv("REDIS_CACHE_TTL", "86400")),
        )
        
        recommendation = RecommendationConfig(
            default_weight_cost=float(os.getenv("DEFAULT_WEIGHT_COST", "0.30")),
            default_weight_availability=float(os.getenv("DEFAULT_WEIGHT_AVAILABILITY", "0.25")),
            default_weight_efficiency=float(os.getenv("DEFAULT_WEIGHT_EFFICIENCY", "0.25")),
            default_weight_thermal=float(os.getenv("DEFAULT_WEIGHT_THERMAL", "0.20")),
        )
        
        rag = RAGConfig(
            unstructured_timeout=int(os.getenv("UNSTRUCTURED_TIMEOUT", "60")),
        )
        
        return cls(
            catalog=catalog,
            cache=cache,
            recommendation=recommendation,
            rag=rag
        )
