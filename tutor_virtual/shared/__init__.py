"""Shared utilities and data transfer objects."""

from .dto import (
    ConverterSpec,
    PreDesignResult,
    LossReport,
    DesignRecommendation,
    ValidationIssue,
)
from .config import AppConfig, CatalogConfig, CacheConfig, RecommendationConfig

__all__ = [
    "ConverterSpec",
    "PreDesignResult",
    "LossReport",
    "DesignRecommendation",
    "ValidationIssue",
    "AppConfig",
    "CatalogConfig",
    "CacheConfig",
    "RecommendationConfig",
]
