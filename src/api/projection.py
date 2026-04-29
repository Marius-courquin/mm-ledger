from datetime import date as _date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import (
    projection_settings, account_classification,
    accounts, connectors, balance_snapshots, loans,
)
from src.schemas.projection import (
    ProjectionSettings, ProjectionSettingsUpdate, ProjectionResult,
    ProjectionPoint, ProjectionStartingState, AccountOverride, AccountCategorization,
)
from src.services.projection_calc import compute_projection
from src.services.loan_calc import compute_loan_state

router = APIRouter(prefix="/api/projection", tags=["projection"])


def _ensure_settings_row(conn):
    """Crée la row id=1 si absente, renvoie la row."""
    row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    if not row:
        conn.execute(insert(projection_settings).values(id=1))
        row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    return row


def _settings_to_dict(row) -> dict:
    return {
        "cash_annual_rate": row.cash_annual_rate,
        "market_annual_rate": row.market_annual_rate,
        "cash_monthly_contribution": row.cash_monthly_contribution,
        "market_monthly_contribution": row.market_monthly_contribution,
        "horizon_years": row.horizon_years,
    }


CASH_CONNECTOR_TYPES = {"woob_bank", "banking"}


def _collect_account_data(engine, user_id: str) -> tuple[dict[str, str], dict[str, float]]:
    """Construit (accounts_by_id, values_by_id) à partir de live data + DB + snapshots.

    accounts_by_id : {account_id: connector_type}
    values_by_id   : {account_id: current_total_value}

    Ordre de priorité pour la valeur : live data → balance_snapshots fallback.
    """
    accounts_by_id: dict[str, str] = {}
    values_by_id: dict[str, float] = {}

    # 1. Connector types depuis DB (référence pour le mapping connector_id → type)
    with engine.connect() as conn:
        connector_types_db = {r.id: r.type for r in conn.execute(select(connectors)).fetchall()}
        # Comptes connus en DB
        for r in conn.execute(
            select(accounts.c.id, accounts.c.connector_id)
        ).fetchall():
            accounts_by_id[r.id] = connector_types_db.get(r.connector_id, "")

    # 2. Live data des workers (priorité)
    if deps.manager:
        all_data = deps.manager.get_user_live_data(user_id)
        for cid, data in all_data.items():
            ctype = connector_types_db.get(cid, "")

            # Balances (cash dans les comptes — TR, BP)
            for b in data.get("balances", []):
                if not isinstance(b, dict):
                    continue
                acc_id = b.get("account_id") or b.get("accountNumber") or ""
                if not acc_id:
                    continue
                accounts_by_id.setdefault(acc_id, ctype)
                amount = float(b.get("amount", 0) or b.get("total_value", 0))
                if amount:
                    values_by_id[acc_id] = values_by_id.get(acc_id, 0.0) + amount

            # Accounts.balance (BP envoie balance dans accounts event)
            for acc in data.get("accounts", []):
                if not isinstance(acc, dict):
                    continue
                acc_id = acc.get("id", "")
                if not acc_id:
                    continue
                accounts_by_id.setdefault(acc_id, ctype)
                balance = acc.get("balance")
                if balance is not None and acc_id not in values_by_id:
                    values_by_id[acc_id] = float(balance)

            # Positions (TR/IBKR : valeur des actifs détenus)
            raw_positions = data.get("positions", [])
            if isinstance(raw_positions, list):
                for acc_data in raw_positions:
                    if not isinstance(acc_data, dict):
                        continue
                    acc_id = (
                        acc_data.get("securitiesAccountNumber")
                        or acc_data.get("account")
                        or acc_data.get("id")
                        or ""
                    )
                    if not acc_id:
                        continue
                    accounts_by_id.setdefault(acc_id, ctype)
                    acc_value = 0.0
                    for cat_data in acc_data.get("categories", []):
                        for pos in cat_data.get("positions", []):
                            cur_raw = pos.get("currentPrice") or pos.get("current_price")
                            cur = float(cur_raw) if cur_raw else 0.0
                            qty = float(pos.get("netSize", 0) or pos.get("quantity", 0))
                            if cur > 0:
                                acc_value += qty * cur
                    if acc_value > 0:
                        values_by_id[acc_id] = values_by_id.get(acc_id, 0.0) + acc_value

    # 3. Fallback snapshots pour les comptes connus mais sans valeur live
    with engine.connect() as conn:
        for acc_id in list(accounts_by_id.keys()):
            if acc_id in values_by_id:
                continue
            row = conn.execute(
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == acc_id)
                .order_by(balance_snapshots.c.date.desc())
                .limit(1)
            ).fetchone()
            if row and row.total_value is not None:
                values_by_id[acc_id] = float(row.total_value)

    return accounts_by_id, values_by_id


def _classify_accounts(accounts_by_id: dict[str, str], overrides: dict[str, str]) -> list[dict]:
    """Applique les overrides sur la classification auto par connector_type."""
    out = []
    for acc_id, ctype in accounts_by_id.items():
        if acc_id in overrides:
            out.append({"account_id": acc_id, "category": overrides[acc_id], "auto": False})
        else:
            cat = "cash" if ctype in CASH_CONNECTOR_TYPES else "market"
            out.append({"account_id": acc_id, "category": cat, "auto": True})
    return out


def _build_state(engine, user_id: str) -> dict:
    """Calcule classifications + cash_initial + market_initial + loans à partir de live + DB + snapshots."""
    accounts_by_id, values_by_id = _collect_account_data(engine, user_id)
    with engine.connect() as conn:
        overrides = {
            r.account_id: r.category
            for r in conn.execute(select(account_classification)).fetchall()
        }
        loan_rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()
    classifications = _classify_accounts(accounts_by_id, overrides)

    cash_total = 0.0
    market_total = 0.0
    for c in classifications:
        v = values_by_id.get(c["account_id"], 0.0)
        if c["category"] == "cash":
            cash_total += v
        else:
            market_total += v

    today = _date.today()
    proj_loans = []
    loan_monthly_total = 0.0
    for l in loan_rows:
        st = compute_loan_state({
            "start_date": l.start_date, "total_months": l.total_months,
            "monthly_payment": l.monthly_payment, "initial_capital": l.initial_capital,
            "archived": l.archived,
        }, today)
        if st["is_active"]:
            loan_monthly_total += float(l.monthly_payment)
            proj_loans.append({
                "monthly_payment": float(l.monthly_payment),
                "end_date": st["end_date"],
            })

    return {
        "classifications": classifications,
        "cash_initial": cash_total,
        "market_initial": market_total,
        "loan_monthly_total": loan_monthly_total,
        "proj_loans": proj_loans,
    }


@router.get("/settings")
def get_settings(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        row = _ensure_settings_row(conn)
    state = _build_state(engine, user.id)
    return {
        "settings": _settings_to_dict(row),
        "classifications": state["classifications"],
    }


@router.put("/settings")
def update_settings(payload: ProjectionSettingsUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        _ensure_settings_row(conn)
        if values:
            conn.execute(update(projection_settings).where(projection_settings.c.id == 1).values(**values))
        row = conn.execute(select(projection_settings).where(projection_settings.c.id == 1)).fetchone()
    return {"settings": _settings_to_dict(row)}


@router.get("/compute", response_model=ProjectionResult)
def compute(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        row = _ensure_settings_row(conn)
    settings = _settings_to_dict(row)
    state = _build_state(engine, user.id)
    today = _date.today()
    points = compute_projection(
        settings, state["cash_initial"], state["market_initial"], state["proj_loans"], today,
    )
    return ProjectionResult(
        settings=ProjectionSettings(**settings),
        starting_state=ProjectionStartingState(
            cash=round(state["cash_initial"], 2),
            market=round(state["market_initial"], 2),
            loan_monthly=round(state["loan_monthly_total"], 2),
        ),
        points=[ProjectionPoint(**p) for p in points],
        classifications=[AccountCategorization(**c) for c in state["classifications"]],
    )


@router.post("/account-override", status_code=status.HTTP_204_NO_CONTENT)
def set_override(payload: AccountOverride, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(account_classification).where(account_classification.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(account_classification)
                .where(account_classification.c.account_id == payload.account_id)
                .values(category=payload.category)
            )
        else:
            conn.execute(insert(account_classification).values(
                account_id=payload.account_id, category=payload.category,
            ))
    return None


@router.delete("/account-override/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_override(account_id: str, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            delete(account_classification).where(account_classification.c.account_id == account_id)
        )
    return None
