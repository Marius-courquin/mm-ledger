from fastapi import APIRouter, HTTPException

from src.api import deps
from src.schemas.vault import PasswordRequest, ChangePasswordRequest, VaultStatusResponse, VaultActionResponse

router = APIRouter(prefix="/api/vault", tags=["vault"])


@router.get("/status", response_model=VaultStatusResponse)
def vault_status():
    return {"state": deps.vault.status}


@router.post("/setup", response_model=VaultActionResponse, status_code=201)
def vault_setup(req: PasswordRequest):
    if deps.vault.status != "uninitialized":
        raise HTTPException(409, "Vault already initialized. Use POST /api/vault/unlock.")
    deps.vault.setup(req.password)
    deps.vault.unlock(req.password)
    return {"status": "created"}


@router.post("/unlock", response_model=VaultActionResponse)
def vault_unlock(req: PasswordRequest):
    if deps.vault.unlock(req.password):
        return {"status": "unlocked"}
    raise HTTPException(401, "Wrong password.")


@router.post("/lock", response_model=VaultActionResponse)
def vault_lock():
    deps.vault.lock()
    return {"status": "locked"}


@router.post("/change-password", response_model=VaultActionResponse)
def vault_change_password(req: ChangePasswordRequest):
    if deps.vault.status != "unlocked":
        raise HTTPException(423, "Vault is locked.")
    if not deps.vault.change_password(req.old_password, req.new_password):
        raise HTTPException(401, "Wrong old password.")
    return {"status": "changed"}
