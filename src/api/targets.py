from datetime import date as _date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, insert, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import targets, target_slices
from src.schemas.targets import (
    TargetCreate, TargetUpdate, TargetResponse,
    SliceCreate, SliceUpdate, SliceResponse,
    ProgressionResponse, HistoryPoint,
)
from src.services.target_progression import (
    compute_current_value, compute_rate, compute_eta, compute_history,
)

router = APIRouter(prefix="/api/targets", tags=["targets"])


def _row_to_target(row, slices: list[SliceResponse]) -> TargetResponse:
    return TargetResponse(
        id=row.id, name=row.name, type=row.type, target_amount=row.target_amount,
        asset_account_id=row.asset_account_id, asset_symbol=row.asset_symbol,
        rate_override=row.rate_override, archived=bool(row.archived),
        created_at=row.created_at, slices=slices,
    )


def _load_slices(conn, target_id: int) -> list[SliceResponse]:
    rows = conn.execute(
        select(target_slices).where(target_slices.c.target_id == target_id)
    ).fetchall()
    return [
        SliceResponse(
            id=r.id, account_id=r.account_id,
            allocation_kind=r.allocation_kind, allocation_value=r.allocation_value,
        )
        for r in rows
    ]


@router.post("", response_model=TargetResponse, status_code=status.HTTP_201_CREATED)
def create_target(payload: TargetCreate, user: AuthUser = Depends(get_current_user)):
    if payload.type == "asset" and (not payload.asset_account_id or not payload.asset_symbol):
        raise HTTPException(400, "Une cible 'asset' nécessite asset_account_id et asset_symbol")
    if payload.type == "bucket" and (payload.asset_account_id or payload.asset_symbol):
        raise HTTPException(400, "Une cible 'bucket' ne porte pas asset_account_id/asset_symbol")
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        result = conn.execute(insert(targets).values(
            name=payload.name, type=payload.type, target_amount=payload.target_amount,
            asset_account_id=payload.asset_account_id, asset_symbol=payload.asset_symbol,
            rate_override=payload.rate_override,
        ))
        target_id = result.inserted_primary_key[0]
        if payload.type == "bucket":
            for s in payload.slices:
                conn.execute(insert(target_slices).values(
                    target_id=target_id, account_id=s.account_id,
                    allocation_kind=s.allocation_kind, allocation_value=s.allocation_value,
                ))
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.get("", response_model=list[TargetResponse])
def list_targets(archived: bool = False, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        stmt = select(targets)
        if not archived:
            stmt = stmt.where(targets.c.archived == 0)
        rows = conn.execute(stmt.order_by(targets.c.id.desc())).fetchall()
        out = [_row_to_target(r, _load_slices(conn, r.id)) for r in rows]
    return out


@router.get("/{target_id}", response_model=TargetResponse)
def get_target(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not row:
            raise HTTPException(404, "Cible introuvable")
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.put("/{target_id}", response_model=TargetResponse)
def update_target(target_id: int, payload: TargetUpdate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    if "archived" in values:
        values["archived"] = 1 if values["archived"] else 0
    with engine.begin() as conn:
        existing = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Cible introuvable")
        if values:
            conn.execute(update(targets).where(targets.c.id == target_id).values(**values))
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        slices = _load_slices(conn, target_id)
    return _row_to_target(row, slices)


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not existing:
            raise HTTPException(404, "Cible introuvable")
        conn.execute(delete(target_slices).where(target_slices.c.target_id == target_id))
        conn.execute(delete(targets).where(targets.c.id == target_id))
    return None


@router.post("/{target_id}/slices", response_model=SliceResponse, status_code=status.HTTP_201_CREATED)
def add_slice(target_id: int, payload: SliceCreate, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        target = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not target:
            raise HTTPException(404, "Cible introuvable")
        if target.type != "bucket":
            raise HTTPException(400, "Les slices ne s'appliquent qu'aux cibles de type 'bucket'")
        result = conn.execute(insert(target_slices).values(
            target_id=target_id, account_id=payload.account_id,
            allocation_kind=payload.allocation_kind, allocation_value=payload.allocation_value,
        ))
        sid = result.inserted_primary_key[0]
    return SliceResponse(
        id=sid, account_id=payload.account_id,
        allocation_kind=payload.allocation_kind, allocation_value=payload.allocation_value,
    )


@router.put("/{target_id}/slices/{slice_id}", response_model=SliceResponse)
def update_slice(target_id: int, slice_id: int, payload: SliceUpdate,
                 user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    values = payload.model_dump(exclude_unset=True)
    with engine.begin() as conn:
        existing = conn.execute(
            select(target_slices).where(target_slices.c.id == slice_id)
                                 .where(target_slices.c.target_id == target_id)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Slice introuvable")
        if values:
            conn.execute(update(target_slices).where(target_slices.c.id == slice_id).values(**values))
        row = conn.execute(select(target_slices).where(target_slices.c.id == slice_id)).fetchone()
    return SliceResponse(
        id=row.id, account_id=row.account_id,
        allocation_kind=row.allocation_kind, allocation_value=row.allocation_value,
    )


@router.delete("/{target_id}/slices/{slice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_slice(target_id: int, slice_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.begin() as conn:
        existing = conn.execute(
            select(target_slices).where(target_slices.c.id == slice_id)
                                 .where(target_slices.c.target_id == target_id)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "Slice introuvable")
        conn.execute(delete(target_slices).where(target_slices.c.id == slice_id))
    return None


@router.get("/{target_id}/progression", response_model=ProgressionResponse)
def get_progression(target_id: int, user: AuthUser = Depends(get_current_user)):
    engine = deps.get_ledger(user.id)
    with engine.connect() as conn:
        row = conn.execute(select(targets).where(targets.c.id == target_id)).fetchone()
        if not row:
            raise HTTPException(404, "Cible introuvable")
        slices_rows = conn.execute(
            select(target_slices).where(target_slices.c.target_id == target_id)
        ).fetchall()

    target = {
        "type": row.type,
        "asset_account_id": row.asset_account_id,
        "asset_symbol": row.asset_symbol,
        "rate_override": row.rate_override,
    }
    slices = [
        {"account_id": s.account_id, "allocation_kind": s.allocation_kind,
         "allocation_value": s.allocation_value}
        for s in slices_rows
    ]
    today = _date.today()
    current = compute_current_value(target, slices, engine, today)
    rate, source = compute_rate(target, slices, engine, today)
    eta_months, eta_status = compute_eta(row.target_amount, current, rate)
    history = compute_history(target, slices, engine, today)
    progress_pct = (current / row.target_amount * 100.0) if row.target_amount > 0 else 0.0

    return ProgressionResponse(
        target_id=target_id,
        target_amount=row.target_amount,
        current_value=current,
        progress_pct=progress_pct,
        rate=rate,
        rate_source=source,
        eta_months=eta_months,
        eta_status=eta_status,
        history=[HistoryPoint(date=p["date"], value=p["value"]) for p in history],
    )
