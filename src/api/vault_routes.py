from fastapi import APIRouter, HTTPException, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.schemas.vault import PasswordRequest, ChangePasswordRequest, VaultStatusResponse, VaultActionResponse

router = APIRouter(prefix="/api/vault", tags=["vault"])


@router.get("/status", response_model=VaultStatusResponse)
def vault_status(user: AuthUser = Depends(get_current_user)):
    return {"state": deps.get_vault(user.id).status}


@router.post("/setup", response_model=VaultActionResponse, status_code=201)
def vault_setup(req: PasswordRequest, user: AuthUser = Depends(get_current_user)):
    vault = deps.get_vault(user.id)
    if vault.status != "uninitialized":
        raise HTTPException(409, "Vault already initialized. Use POST /api/vault/unlock.")
    vault.setup(req.password)
    vault.unlock(req.password)
    return {"status": "created"}


@router.post("/unlock", response_model=VaultActionResponse)
def vault_unlock(req: PasswordRequest, user: AuthUser = Depends(get_current_user)):
    vault = deps.get_vault(user.id)
    if vault.unlock(req.password):
        return {"status": "unlocked"}
    raise HTTPException(401, "Wrong password.")


@router.post("/lock", response_model=VaultActionResponse)
def vault_lock(user: AuthUser = Depends(get_current_user)):
    deps.get_vault(user.id).lock()
    return {"status": "locked"}


@router.post("/change-password", response_model=VaultActionResponse)
def vault_change_password(req: ChangePasswordRequest, user: AuthUser = Depends(get_current_user)):
    vault = deps.get_vault(user.id)
    if vault.status != "unlocked":
        raise HTTPException(423, "Vault is locked.")
    if not vault.change_password(req.old_password, req.new_password):
        raise HTTPException(401, "Wrong old password.")
    return {"status": "changed"}
