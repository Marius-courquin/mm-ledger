import shutil
import logging

from fastapi import APIRouter, HTTPException, Response, Request

from src.api import deps
from src.auth import hash_password, verify_password, create_jwt, get_or_create_jwt_secret, LoginRateLimiter
from src.api.middleware import set_jwt_secret, get_current_user
from src.db.app_db import create_user, get_user_by_username, count_admins
from src.config import JWT_SECRET_FILE, VAULT_DB, LEDGER_DB, USERS_DIR


def _migrate_legacy_data(user_id: str):
    """Move old single-user data/vault.db and data/ledger.db to data/users/{user_id}/"""
    log = logging.getLogger("migration")
    user_dir = USERS_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    if VAULT_DB.exists():
        shutil.move(str(VAULT_DB), str(user_dir / "vault.db"))
        log.info(f"Migrated legacy vault.db to {user_dir}")
    if LEDGER_DB.exists():
        shutil.move(str(LEDGER_DB), str(user_dir / "ledger.db"))
        log.info(f"Migrated legacy ledger.db to {user_dir}")

router = APIRouter(prefix="/api/auth", tags=["auth"])
_rate_limiter = LoginRateLimiter()


@router.get("/status")
def auth_status(request: Request):
    if not deps.app_db:
        return {"state": "no_admin"}
    admins = count_admins(deps.app_db)
    if admins == 0:
        return {"state": "no_admin"}
    token = request.cookies.get("mm_session")
    if token:
        from src.auth import decode_jwt
        payload = decode_jwt(token, deps.jwt_secret)
        if payload:
            return {
                "state": "logged_in",
                "user": {"id": payload["user_id"], "username": payload["username"], "role": payload["role"]},
            }
    return {"state": "logged_out"}


@router.post("/setup", status_code=201)
def auth_setup(request_body: dict, response: Response):
    username = request_body.get("username", "").strip()
    password = request_body.get("password", "")
    if len(username) < 3:
        raise HTTPException(400, "Nom d'utilisateur: 3 caractères minimum")
    if len(password) < 8:
        raise HTTPException(400, "Mot de passe: 8 caractères minimum")
    if count_admins(deps.app_db) > 0:
        raise HTTPException(409, "Un administrateur existe déjà")
    deps.jwt_secret = get_or_create_jwt_secret(JWT_SECRET_FILE)
    set_jwt_secret(deps.jwt_secret)
    user = create_user(deps.app_db, username, hash_password(password), "admin")
    _migrate_legacy_data(user["id"])
    token = create_jwt({"user_id": user["id"], "username": user["username"], "role": "admin"}, deps.jwt_secret)
    response.set_cookie("mm_session", token, httponly=True, samesite="lax", max_age=86400)
    return {"status": "created", "user": {"id": user["id"], "username": user["username"], "role": "admin"}}


@router.post("/login")
def auth_login(request_body: dict, response: Response):
    username = request_body.get("username", "").strip()
    password = request_body.get("password", "")
    if not _rate_limiter.is_allowed(username):
        raise HTTPException(429, "Trop de tentatives. Réessayez dans quelques minutes.")
    user = get_user_by_username(deps.app_db, username)
    if not user or not verify_password(password, user["password_hash"]):
        _rate_limiter.record_failure(username)
        raise HTTPException(401, "Identifiants incorrects")
    _rate_limiter.record_success(username)
    token = create_jwt({"user_id": user["id"], "username": user["username"], "role": user["role"]}, deps.jwt_secret)
    response.set_cookie("mm_session", token, httponly=True, samesite="lax", max_age=86400)
    return {"status": "ok", "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@router.post("/logout")
def auth_logout(request: Request, response: Response):
    try:
        user = get_current_user(request)
        if deps.manager and hasattr(deps.manager, 'stop_user_workers'):
            deps.manager.stop_user_workers(user.id)
        deps.cleanup_user(user.id)
    except Exception:
        pass
    response.delete_cookie("mm_session")
    return {"status": "logged_out"}
