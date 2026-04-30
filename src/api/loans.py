from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import loans, loan_account_link
from src.schemas.loans import LoanCreate, LoanUpdate, LoanResponse, LoanSummary, LoanCandidate, LinkRequest, FromAccountRequest
from src.services.loan_calc import compute_loan_state

router = APIRouter(prefix="/api/loans", tags=["loans"])


def _row_to_response(row, today: _date) -> LoanResponse:
    state = compute_loan_state({
        "start_date": row.start_date,
        "total_months": row.total_months,
        "monthly_payment": row.monthly_payment,
        "initial_capital": row.initial_capital,
        "archived": row.archived,
    }, today)
    return LoanResponse(
        id=row.id, name=row.name, loan_type=row.loan_type,
        initial_capital=row.initial_capital, monthly_payment=row.monthly_payment,
        total_months=row.total_months, start_date=row.start_date,
        archived=bool(row.archived), created_at=row.created_at,
        end_date=state["end_date"], months_paid=state["months_paid"],
        months_remaining=state["months_remaining"],
        amount_remaining=state["amount_remaining"],
        progress_pct=state["progress_pct"], is_active=state["is_active"],
    )


@router.post("", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
def create_loan(payload: LoanCreate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(loans).values(
            name=payload.name, loan_type=payload.loan_type,
            initial_capital=payload.initial_capital, monthly_payment=payload.monthly_payment,
            total_months=payload.total_months, start_date=payload.start_date,
        ))
        lid = result.inserted_primary_key[0]
        row = conn.execute(select(loans).where(loans.c.id == lid)).fetchone()
    return _row_to_response(row, _date.today())


@router.get("", response_model=list[LoanResponse])
def list_loans(archived: bool = False, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        stmt = select(loans)
        if not archived:
            stmt = stmt.where(loans.c.archived == 0)
        rows = conn.execute(stmt.order_by(loans.c.id.desc())).fetchall()
    today = _date.today()
    return [_row_to_response(r, today) for r in rows]


@router.get("/summary", response_model=LoanSummary)
def loans_summary(user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()
    today = _date.today()
    states = [(r, compute_loan_state({
        "start_date": r.start_date, "total_months": r.total_months,
        "monthly_payment": r.monthly_payment, "initial_capital": r.initial_capital,
        "archived": r.archived,
    }, today)) for r in rows]
    active = [(r, s) for r, s in states if s["is_active"]]
    return LoanSummary(
        total_monthly_payment=round(sum(r.monthly_payment for r, _ in active), 2),
        total_amount_remaining=round(sum(s["amount_remaining"] for _, s in active), 2),
        last_end_date=max((s["end_date"] for _, s in active), default=None),
        active_count=len(active),
    )


@router.get("/candidates", response_model=list[LoanCandidate])
def list_candidates(user: AuthUser = Depends(get_current_user)):
    """Liste les comptes liability détectés non liés non ignorés."""
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        link_rows = conn.execute(select(loan_account_link)).fetchall()
    links_by_id = {r.account_id: r for r in link_rows}

    out: list[LoanCandidate] = []
    all_data = deps.manager.get_user_live_data(user.id)
    for _cid, data in all_data.items():
        balances_by_id = {b.account_id: b for b in data.get("balances", [])}
        for acc in data.get("accounts", []):
            if acc.kind != "liability":
                continue
            link = links_by_id.get(acc.id)
            if link and (link.loan_id is not None or link.ignored):
                continue
            bal = balances_by_id.get(acc.id)
            out.append(LoanCandidate(
                account_id=acc.id,
                label=acc.label,
                balance=float(bal.total_value) if bal else 0.0,
                currency=bal.currency if bal else acc.currency,
                connector_type=acc.connector_type,
                as_of=bal.as_of if bal else None,
            ))
    return out


@router.post("/{loan_id}/link", response_model=LoanResponse)
def link_account(
    loan_id: int, payload: LinkRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Crée ou met à jour un lien prêt ↔ compte bancaire (account_id canonical)."""
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        loan_row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not loan_row:
            raise HTTPException(404, "Prêt introuvable")
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == payload.account_id
                ).values(loan_id=loan_id, ignored=0)
            )
        else:
            conn.execute(insert(loan_account_link).values(
                account_id=payload.account_id, loan_id=loan_id, ignored=0,
            ))
    return _row_to_response(loan_row, _date.today())


@router.delete("/{loan_id}/link", status_code=status.HTTP_204_NO_CONTENT)
def unlink_account(loan_id: int, user: AuthUser = Depends(get_current_user)):
    """Détache le compte (loan_id → NULL). ignored reste à 0 (le candidat réapparaît)."""
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            update(loan_account_link).where(
                loan_account_link.c.loan_id == loan_id
            ).values(loan_id=None)
        )
    return None


@router.post("/candidates/{account_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def ignore_candidate(account_id: str, user: AuthUser = Depends(get_current_user)):
    """Marque un candidat comme ignoré (n'apparaîtra plus dans la liste)."""
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == account_id
                ).values(ignored=1)
            )
        else:
            conn.execute(insert(loan_account_link).values(
                account_id=account_id, ignored=1,
            ))
    return None


@router.delete("/candidates/{account_id}/ignore", status_code=status.HTTP_204_NO_CONTENT)
def unignore_candidate(account_id: str, user: AuthUser = Depends(get_current_user)):
    """Annule l'état ignoré (le compte redevient candidat)."""
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        conn.execute(
            update(loan_account_link).where(
                loan_account_link.c.account_id == account_id
            ).values(ignored=0)
        )
    return None


@router.post("/from-account", response_model=LoanResponse, status_code=status.HTTP_201_CREATED)
def create_from_account(
    payload: FromAccountRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Crée un loan + crée le lien vers account_id en une seule transaction."""
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(loans).values(
            name=payload.name, loan_type=payload.loan_type,
            initial_capital=payload.initial_capital,
            monthly_payment=payload.monthly_payment,
            total_months=payload.total_months,
            start_date=payload.start_date,
        ))
        lid = result.inserted_primary_key[0]
        existing = conn.execute(
            select(loan_account_link).where(loan_account_link.c.account_id == payload.account_id)
        ).fetchone()
        if existing:
            conn.execute(
                update(loan_account_link).where(
                    loan_account_link.c.account_id == payload.account_id
                ).values(loan_id=lid, ignored=0)
            )
        else:
            conn.execute(insert(loan_account_link).values(
                account_id=payload.account_id, loan_id=lid, ignored=0,
            ))
        row = conn.execute(select(loans).where(loans.c.id == lid)).fetchone()
    return _row_to_response(row, _date.today())


@router.get("/{loan_id}", response_model=LoanResponse)
def get_loan(loan_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not row:
            raise HTTPException(404, "Prêt introuvable")
    return _row_to_response(row, _date.today())


@router.put("/{loan_id}", response_model=LoanResponse)
def update_loan(loan_id: int, payload: LoanUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    if "archived" in values:
        values["archived"] = 1 if values["archived"] else 0
    with engine.begin() as conn:
        existing = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Prêt introuvable")
        if values:
            conn.execute(update(loans).where(loans.c.id == loan_id).values(**values))
        row = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
    return _row_to_response(row, _date.today())


@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_loan(loan_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(loans).where(loans.c.id == loan_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Prêt introuvable")
        conn.execute(delete(loans).where(loans.c.id == loan_id))
    return None
