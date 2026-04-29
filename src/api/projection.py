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
from src.services.account_categorization import categorize_accounts
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


def _starting_state(engine, classifications: list[dict]) -> tuple[float, float, float, list[dict]]:
    """Renvoie (cash_initial, market_initial, loan_monthly_total, active_loans_for_proj)."""
    cls_by_acc = {c["account_id"]: c["category"] for c in classifications}
    cash_total = 0.0
    market_total = 0.0
    with engine.connect() as conn:
        # Solde le plus récent par compte
        for acc_id, cat in cls_by_acc.items():
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == acc_id)
                .order_by(balance_snapshots.c.date.desc())
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            v = float(row.total_value) if row and row.total_value is not None else 0.0
            if cat == "cash":
                cash_total += v
            else:
                market_total += v
        loan_rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()
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
    return cash_total, market_total, loan_monthly_total, proj_loans


@router.get("/settings")
def get_settings(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        row = _ensure_settings_row(conn)
    classifications = categorize_accounts(engine)
    return {
        "settings": _settings_to_dict(row),
        "classifications": classifications,
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
    classifications = categorize_accounts(engine)
    cash_initial, market_initial, loan_monthly, proj_loans = _starting_state(engine, classifications)
    today = _date.today()
    points = compute_projection(settings, cash_initial, market_initial, proj_loans, today)
    return ProjectionResult(
        settings=ProjectionSettings(**settings),
        starting_state=ProjectionStartingState(
            cash=round(cash_initial, 2), market=round(market_initial, 2),
            loan_monthly=round(loan_monthly, 2),
        ),
        points=[ProjectionPoint(**p) for p in points],
        classifications=[AccountCategorization(**c) for c in classifications],
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
