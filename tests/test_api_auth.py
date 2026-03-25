def test_auth_status_no_admin(client):
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "no_admin"


def test_auth_setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "admin"


def test_auth_setup_duplicate(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/setup", json={"username": "admin2", "password": "password123"})
    assert r.status_code == 409


def test_auth_login(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert r.status_code == 200


def test_auth_login_wrong_password(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_auth_status_logged_in(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "logged_in"
    assert r.json()["user"]["username"] == "admin"


def test_auth_logout(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "logged_out"


def test_password_too_short(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "short"})
    assert r.status_code == 400
