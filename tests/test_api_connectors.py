def _setup_vault(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})


def test_create_connector(client):
    _setup_vault(client)
    r = client.post("/api/connectors", json={
        "id": "tr_1", "type": "trade_republic", "label": "TR",
        "credentials": {"phone": "+33", "pin": "1234"}, "config": {}
    })
    assert r.status_code == 201
    assert r.json()["id"] == "tr_1"


def test_create_connector_vault_locked(client):
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


def test_get_connector_types(client):
    r = client.get("/api/connectors/types")
    assert r.status_code == 200
    types = {t["type"] for t in r.json()}
    assert "trade_republic" in types
    assert "ibkr" in types
    assert "woob_bank" in types
