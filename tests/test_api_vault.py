def test_vault_status_uninitialized(client):
    r = client.get("/api/vault/status")
    assert r.status_code == 200
    assert r.json()["state"] == "uninitialized"


def test_vault_setup(client):
    r = client.post("/api/vault/setup", json={"password": "test"})
    assert r.status_code == 201
    r = client.get("/api/vault/status")
    assert r.json()["state"] == "locked"


def test_vault_setup_duplicate(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/setup", json={"password": "test2"})
    assert r.status_code == 409


def test_vault_unlock(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/unlock", json={"password": "test"})
    assert r.status_code == 200
    assert r.json()["status"] == "unlocked"


def test_vault_unlock_wrong_password(client):
    client.post("/api/vault/setup", json={"password": "test"})
    r = client.post("/api/vault/unlock", json={"password": "wrong"})
    assert r.status_code == 401


def test_vault_lock(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})
    r = client.post("/api/vault/lock")
    assert r.status_code == 200
    r = client.get("/api/vault/status")
    assert r.json()["state"] == "locked"


def test_vault_change_password(client):
    client.post("/api/vault/setup", json={"password": "old"})
    client.post("/api/vault/unlock", json={"password": "old"})
    r = client.post("/api/vault/change-password", json={"old_password": "old", "new_password": "new"})
    assert r.status_code == 200
    client.post("/api/vault/lock")
    r = client.post("/api/vault/unlock", json={"password": "new"})
    assert r.status_code == 200
