"""ABC commun à tous les normalizers."""
from abc import ABC, abstractmethod
from typing import Any

from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition


class Normalizer(ABC):
    """Convertit le raw d'un connecteur en types canonical.

    Les méthodes `normalize_balances` et `normalize_positions` reçoivent les
    `accounts` déjà normalisés pour pouvoir matcher les soldes/positions à
    leur compte par ID canonical.
    """

    @abstractmethod
    def normalize_accounts(self, raw: Any, connector_id: str) -> list[CanonicalAccount]: ...

    @abstractmethod
    def normalize_balances(
        self, raw: Any, accounts: list[CanonicalAccount]
    ) -> list[CanonicalBalance]: ...

    @abstractmethod
    def normalize_positions(
        self, raw: Any, accounts: list[CanonicalAccount]
    ) -> list[CanonicalPosition]: ...
