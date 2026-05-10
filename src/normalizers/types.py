"""Canonical types pour Comptes / Soldes / Positions.

Tout connecteur produit ces types via son Normalizer dédié. Aucun consommateur
(API, scheduler, snapshot) ne doit interpréter du raw connecteur — uniquement
ces shapes.
"""
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

AccountKind = Literal["cash", "securities", "liability"]

TaxWrapper = Literal[
    "none", "cto", "pea", "pea_pme", "per", "av",
    "livret_a", "livret_jeune", "ldds", "lep", "cel", "pel",
]

AssetClass = Literal["equity", "etf", "bond", "crypto", "private", "other"]


class CanonicalAccount(BaseModel):
    """Compte normalisé, identifiant stable cross-sync."""

    id: str = Field(..., description="ID stable préfixé par connecteur (tr:, ibkr:, woob:..., eb:)")
    connector_id: str
    connector_type: str
    label: str
    kind: AccountKind
    tax_wrapper: TaxWrapper = "none"
    currency: str = "EUR"


class CanonicalBalance(BaseModel):
    """Solde d'un compte. Pour kind=liability, total_value est négatif (dette)."""

    account_id: str
    cash: Decimal | None = None
    positions_value: Decimal | None = None
    total_value: Decimal
    currency: str = "EUR"
    as_of: datetime


class CanonicalPosition(BaseModel):
    account_id: str
    symbol: str
    isin: str | None = None
    name: str
    quantity: Decimal
    average_price: Decimal | None = None
    current_price: Decimal | None = None
    value: Decimal
    asset_class: AssetClass
    currency: str = "EUR"
