import shutil
from fastapi import APIRouter, HTTPException, Depends

from src.api import deps
from src.api.middleware import require_admin, AuthUser, deny_user
from src.auth import hash_password
from src.db.app_db import create_user, list_users, delete_user, get_user_by_username, count_admins, get_user_by_id, update_password
from src.config import USERS_DIR

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def admin_list_users(user: AuthUser = Depends(require_admin)):
    return list_users(deps.app_db)


@router.post("/users", status_code=201)
def admin_create_user(body: dict, user: AuthUser = Depends(require_admin)):
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "user")
    if len(username) < 3:
        raise HTTPException(400, "Nom d'utilisateur: 3 caractères minimum")
    if len(password) < 8:
        raise HTTPException(400, "Mot de passe: 8 caractères minimum")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Rôle invalide")
    if get_user_by_username(deps.app_db, username):
        raise HTTPException(409, "Ce nom d'utilisateur est déjà pris")
    new_user = create_user(deps.app_db, username, hash_password(password), role)
    return new_user


@router.put("/users/{user_id}")
def admin_update_user(user_id: str, body: dict, user: AuthUser = Depends(require_admin)):
    target = get_user_by_id(deps.app_db, user_id)
    if not target:
        raise HTTPException(404, "Utilisateur introuvable")
    password = body.get("password", "")
    if password:
        if len(password) < 8:
            raise HTTPException(400, "Mot de passe: 8 caractères minimum")
        update_password(deps.app_db, user_id, hash_password(password))
    return {"status": "updated"}


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, user: AuthUser = Depends(require_admin)):
    target = get_user_by_id(deps.app_db, user_id)
    if not target:
        raise HTTPException(404, "Utilisateur introuvable")
    if target["role"] == "admin" and count_admins(deps.app_db) <= 1:
        raise HTTPException(403, "Impossible de supprimer le dernier administrateur")
    if hasattr(deps.manager, 'stop_user_workers'):
        deps.manager.stop_user_workers(user_id)
    deps.cleanup_user(user_id)
    deny_user(user_id)
    user_dir = USERS_DIR / user_id
    if user_dir.exists():
        shutil.rmtree(user_dir)
    delete_user(deps.app_db, user_id)
