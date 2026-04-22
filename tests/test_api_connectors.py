def _setup_auth(client):
    """Create admin user and get authenticated session."""
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201


def _setup_vault(client):
    _setup_auth(client)
    client.post("/api/vault/setup", json={"password": "test"})


def test_create_connector(client):
    _setup_vault(client)
    r = client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33", "pin": "1234"}, "config": {}
    })
    assert r.status_code == 201
    assert r.json()["id"] == "tr_1"


def test_create_connector_vault_locked(client):
    _setup_auth(client)
    r = client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {}, "config": {}
    })
    assert r.status_code == 423


def test_list_connectors(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.get("/api/connectors")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == "tr_1"
    assert "credentials" not in str(r.json())


def test_update_connector(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.put("/api/connectors/tr_1", json={"label": "TR Updated"})
    assert r.status_code == 200
    assert r.json()["label"] == "TR Updated"


def test_delete_connector(client):
    _setup_vault(client)
    client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33"}, "config": {}
    })
    r = client.delete("/api/connectors/tr_1")
    assert r.status_code == 204
    r = client.get("/api/connectors")
    assert len(r.json()) == 0


def test_get_connector_types_includes_ibkr_vault_fields(client):
    response = client.get("/api/connectors/types")
    assert response.status_code == 200
    types = response.json()
    ibkr = next((t for t in types if t["type"] == "ibkr"), None)
    assert ibkr is not None

    names = {f["name"] for f in ibkr["credential_fields"]}
    assert names == {"username", "password", "trading_mode"}

    pwd = next(f for f in ibkr["credential_fields"] if f["name"] == "password")
    assert pwd["type"] == "password"

    tm = next(f for f in ibkr["credential_fields"] if f["name"] == "trading_mode")
    assert tm["type"] == "select"
    assert {o["value"] for o in tm["options"]} == {"live", "paper"}

    assert ibkr["config_fields"] == []
