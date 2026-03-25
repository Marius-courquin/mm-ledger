import tempfile
from pathlib import Path
from src.auth import hash_password, verify_password, create_jwt, decode_jwt, LoginRateLimiter
from src.db.app_db import create_app_db, create_user, get_user_by_username, list_users, delete_user


def test_password_hash_and_verify():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    secret = "testsecret123"
    token = create_jwt({"user_id": "abc", "username": "marius", "role": "admin"}, secret, expires_hours=1)
    payload = decode_jwt(token, secret)
    assert payload["user_id"] == "abc"
    assert payload["username"] == "marius"
    assert payload["role"] == "admin"


def test_jwt_expired():
    secret = "testsecret123"
    token = create_jwt({"user_id": "abc", "username": "m", "role": "admin"}, secret, expires_hours=-1)
    assert decode_jwt(token, secret) is None


def test_rate_limiter():
    rl = LoginRateLimiter(max_attempts=3, window_seconds=60)
    assert rl.is_allowed("marius")
    rl.record_failure("marius")
    rl.record_failure("marius")
    rl.record_failure("marius")
    assert not rl.is_allowed("marius")
    rl.record_success("marius")
    assert rl.is_allowed("marius")


def test_app_db_crud():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_app_db(Path(tmp) / "app.db")
        user = create_user(engine, "marius", hash_password("pass"), "admin")
        assert user["username"] == "marius"
        assert user["role"] == "admin"

        found = get_user_by_username(engine, "marius")
        assert found is not None
        assert found["username"] == "marius"

        users = list_users(engine)
        assert len(users) == 1

        delete_user(engine, user["id"])
        assert get_user_by_username(engine, "marius") is None
