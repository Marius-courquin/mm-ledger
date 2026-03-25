import time
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
from jose import jwt, JWTError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_jwt(payload: dict, secret: str, expires_hours: int = 24) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    return jwt.encode({**payload, "exp": exp}, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        return None


def get_or_create_jwt_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text().strip()
    secret = secrets.token_urlsafe(48)
    path.write_text(secret)
    path.chmod(0o600)
    return secret


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self._max = max_attempts
        self._window = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_allowed(self, username: str) -> bool:
        now = time.time()
        attempts = self._attempts.get(username, [])
        attempts = [t for t in attempts if now - t < self._window]
        self._attempts[username] = attempts
        return len(attempts) < self._max

    def record_failure(self, username: str):
        self._attempts.setdefault(username, []).append(time.time())

    def record_success(self, username: str):
        self._attempts.pop(username, None)
