def _setup_admin(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})


def test_admin_list_users(client):
    _setup_admin(client)
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_admin_create_user(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123", "role": "user"})
    assert r.status_code == 201
    assert r.json()["username"] == "magni"
    r = client.get("/api/admin/users")
    assert len(r.json()) == 2


def test_admin_create_duplicate(client):
    _setup_admin(client)
    client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    assert r.status_code == 409


def test_admin_delete_user(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    uid = r.json()["id"]
    r = client.delete(f"/api/admin/users/{uid}")
    assert r.status_code == 204


def test_admin_cannot_delete_last_admin(client):
    _setup_admin(client)
    r = client.get("/api/admin/users")
    admin_id = r.json()[0]["id"]
    r = client.delete(f"/api/admin/users/{admin_id}")
    assert r.status_code == 403


def test_admin_reset_password(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    uid = r.json()["id"]
    r = client.put(f"/api/admin/users/{uid}", json={"password": "newpassword123"})
    assert r.status_code == 200


def test_non_admin_cannot_access(client):
    _setup_admin(client)
    client.post("/api/admin/users", json={"username": "magni", "password": "password123", "role": "user"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "magni", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 403
