from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import insert, select, update, delete

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import connectors
from src.schemas.connector import (
    ConnectorCreate, ConnectorUpdate, ConnectorResponse, WorkerInfo, TwoFARequest,
)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

CONNECTOR_TYPES = [
    {
        "type": "trade_republic", "label": "Trade Republic",
        "credential_fields": [
            {"name": "phone", "type": "text", "required": True, "placeholder": "+33612345678"},
            {"name": "pin", "type": "password", "required": True, "placeholder": "1234"},
        ],
        "config_fields": [], "supports_2fa": True, "supports_streaming": True,
    },
    {
        "type": "ibkr", "label": "Interactive Brokers",
        "credential_fields": [],
        "config_fields": [
            {"name": "host", "type": "text", "required": True, "default": "127.0.0.1"},
            {"name": "port", "type": "number", "required": True, "default": 4001},
        ],
        "supports_2fa": False, "supports_streaming": True,
    },
    {
        "type": "woob_bank", "label": "Banque Populaire",
        "credential_fields": [
            {"name": "login", "type": "text", "required": True},
            {"name": "password", "type": "password", "required": True},
            {"name": "bank_module", "type": "text", "required": True, "default": "banquepopulaire"},
            {"name": "region", "type": "text", "required": False, "placeholder": "10207"},
        ],
        "config_fields": [], "supports_2fa": True, "supports_streaming": False,
    },
]


def _require_vault(user: AuthUser):
    if deps.get_vault(user.id).status != "unlocked":
        raise HTTPException(423, "Vault is locked. POST /api/vault/unlock first.")


@router.get("/types")
def get_connector_types():
    return CONNECTOR_TYPES


@router.get("", response_model=list[ConnectorResponse])
def list_connectors(user: AuthUser = Depends(get_current_user)):
    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(select(connectors)).fetchall()
    result = []
    for row in rows:
        worker_status = deps.manager.get_status(f"{user.id}:{row.id}")
        result.append(ConnectorResponse(
            id=row.id, type=row.type, label=row.label, config=row.config or {},
            worker=WorkerInfo(**worker_status),
        ))
    return result


def _slugify(text: str) -> str:
    import unicodedata, re
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return text or "connector"


@router.post("", response_model=ConnectorResponse, status_code=201)
def create_connector(req: ConnectorCreate, user: AuthUser = Depends(get_current_user)):
    _require_vault(user)
    connector_id = req.id or _slugify(req.label)
    with deps.get_ledger(user.id).begin() as conn:
        conn.execute(insert(connectors).values(
            id=connector_id, type=req.type, label=req.label, config=req.config,
        ))
    deps.get_vault(user.id).store(connector_id, req.type, req.label, req.credentials)
    return ConnectorResponse(id=connector_id, type=req.type, label=req.label, config=req.config)


@router.put("/{connector_id}", response_model=ConnectorResponse)
def update_connector(connector_id: str, req: ConnectorUpdate, user: AuthUser = Depends(get_current_user)):
    updates = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.config is not None:
        updates["config"] = req.config
    if updates:
        with deps.get_ledger(user.id).begin() as conn:
            conn.execute(update(connectors).where(connectors.c.id == connector_id).values(**updates))
    if req.credentials is not None:
        _require_vault(user)
        with deps.get_ledger(user.id).connect() as conn:
            row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
        if not row:
            raise HTTPException(404, "Connector not found.")
        deps.get_vault(user.id).store(connector_id, row.type, req.label or row.label, req.credentials)
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    if not row:
        raise HTTPException(404, "Connector not found.")
    return ConnectorResponse(id=row.id, type=row.type, label=row.label, config=row.config or {})


@router.delete("/{connector_id}", status_code=204)
def delete_connector(connector_id: str, user: AuthUser = Depends(get_current_user)):
    deps.manager.stop(f"{user.id}:{connector_id}")
    deps.get_vault(user.id).delete(connector_id)
    with deps.get_ledger(user.id).begin() as conn:
        conn.execute(delete(connectors).where(connectors.c.id == connector_id))


@router.get("/{connector_id}/status")
def get_connector_status(connector_id: str, user: AuthUser = Depends(get_current_user)):
    return {"id": connector_id, **deps.manager.get_status(f"{user.id}:{connector_id}")}


@router.post("/{connector_id}/connect", status_code=202)
def connect_connector(connector_id: str, user: AuthUser = Depends(get_current_user)):
    _require_vault(user)
    creds = deps.get_vault(user.id).retrieve(connector_id)
    if creds is None:
        raise HTTPException(404, "Connector not found.")
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    if not row:
        raise HTTPException(404, "Connector not found.")
    deps.manager.spawn(f"{user.id}:{connector_id}", row.type, creds)
    return {"status": "connecting"}


@router.post("/{connector_id}/disconnect")
def disconnect_connector(connector_id: str, user: AuthUser = Depends(get_current_user)):
    deps.manager.stop(f"{user.id}:{connector_id}")
    return {"status": "disconnected"}


@router.post("/{connector_id}/restart", status_code=202)
def restart_connector(connector_id: str, user: AuthUser = Depends(get_current_user)):
    _require_vault(user)
    deps.manager.stop(f"{user.id}:{connector_id}")
    creds = deps.get_vault(user.id).retrieve(connector_id)
    if creds is None:
        raise HTTPException(404, "Connector not found.")
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(select(connectors).where(connectors.c.id == connector_id)).fetchone()
    deps.manager.spawn(f"{user.id}:{connector_id}", row.type, creds)
    return {"status": "connecting"}


@router.post("/{connector_id}/2fa")
def submit_2fa(connector_id: str, req: TwoFARequest, user: AuthUser = Depends(get_current_user)):
    status = deps.manager.get_status(f"{user.id}:{connector_id}")
    if status["state"] != "waiting_2fa":
        raise HTTPException(409, f"Worker is not in waiting_2fa state. Current state: {status['state']}")
    deps.manager.send_command(f"{user.id}:{connector_id}", {"type": "submit_2fa", "code": req.code})
    return {"status": "submitted"}
