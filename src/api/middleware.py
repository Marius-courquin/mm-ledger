from fastapi import Request, HTTPException

from src.auth import decode_jwt

_denied_users: set[str] = set()
_jwt_secret: str = ""


def set_jwt_secret(secret: str):
    global _jwt_secret
    _jwt_secret = secret


def deny_user(user_id: str):
    _denied_users.add(user_id)


class AuthUser:
    def __init__(self, id: str, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role


def get_current_user(request: Request) -> AuthUser:
    token = request.cookies.get("mm_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    payload = decode_jwt(token, _jwt_secret)
    if not payload:
        raise HTTPException(401, "Session expirée")
    uid = payload.get("user_id")
    if uid in _denied_users:
        raise HTTPException(401, "Compte supprimé")
    return AuthUser(id=uid, username=payload["username"], role=payload["role"])


def require_admin(request: Request) -> AuthUser:
    user = get_current_user(request)
    if user.role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user
