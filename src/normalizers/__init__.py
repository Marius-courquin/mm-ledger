"""Registry des normalizers par connector_type."""
from src.normalizers.base import Normalizer
from src.normalizers.types import (
    AccountKind,
    AssetClass,
    CanonicalAccount,
    CanonicalBalance,
    CanonicalPosition,
    TaxWrapper,
)

_REGISTRY: dict[str, Normalizer] = {}


def register(connector_type: str, normalizer: Normalizer) -> None:
    _REGISTRY[connector_type] = normalizer


def get_normalizer(connector_type: str) -> Normalizer | None:
    return _REGISTRY.get(connector_type)


__all__ = [
    "Normalizer", "AccountKind", "AssetClass", "TaxWrapper",
    "CanonicalAccount", "CanonicalBalance", "CanonicalPosition",
    "register", "get_normalizer",
]
