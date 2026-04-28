from sqlalchemy import insert
from src.db.models import connectors, accounts, balance_snapshots
from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    payload = decode_jwt(token, deps.jwt_secret)
    return payload["user_id"]


def _seed_account(user_id, account_id="acc1", value=10000):
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c1", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="c1", name="A", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id=account_id, date="2026-04-27",
            cash=0, positions_value=value, total_value=value,
            positions=[{"symbol": "VWCE", "qty": 10, "price": value/10, "value": value}],
        ))


def test_create_asset_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    r = client.post("/api/targets", json={
        "name": "5K sur VWCE", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "5K sur VWCE"
    assert body["type"] == "asset"
    assert body["id"] > 0


def test_create_bucket_target(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    r = client.post("/api/targets", json={
        "name": "Apport immo", "type": "bucket", "target_amount": 20000,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50}]
    })
    assert r.status_code == 201
    body = r.json()
    assert body["type"] == "bucket"
    assert len(body["slices"]) == 1


def test_list_targets(client):
    user_id = _setup(client)
    _seed_account(user_id)
    client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    client.post("/api/targets", json={"name": "T2", "type": "bucket", "target_amount": 2000, "slices": []})
    r = client.get("/api/targets")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}")
    assert r.status_code == 200
    assert r.json()["name"] == "T1"


def test_get_target_404(client):
    _setup(client)
    r = client.get("/api/targets/9999")
    assert r.status_code == 404


def test_update_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.put(f"/api/targets/{tid}", json={"name": "T1 renamed", "target_amount": 1500})
    assert r.status_code == 200
    assert r.json()["name"] == "T1 renamed"
    assert r.json()["target_amount"] == 1500


def test_delete_target(client):
    user_id = _setup(client)
    _seed_account(user_id)
    cr = client.post("/api/targets", json={"name": "T1", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.delete(f"/api/targets/{tid}")
    assert r.status_code == 204
    r = client.get(f"/api/targets/{tid}")
    assert r.status_code == 404


def test_unauth(client):
    r = client.get("/api/targets")
    assert r.status_code == 401


def test_add_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={"name": "T", "type": "bucket", "target_amount": 1000, "slices": []})
    tid = cr.json()["id"]
    r = client.post(f"/api/targets/{tid}/slices", json={
        "account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50
    })
    assert r.status_code == 201
    assert r.json()["account_id"] == "acc1"
    g = client.get(f"/api/targets/{tid}").json()
    assert len(g["slices"]) == 1


def test_add_slice_to_asset_target_rejected(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 1000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.post(f"/api/targets/{tid}/slices", json={
        "account_id": "acc1", "allocation_kind": "percent", "allocation_value": 50
    })
    assert r.status_code == 400


def test_update_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 1000,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 30}]
    })
    tid = cr.json()["id"]
    sid = cr.json()["slices"][0]["id"]
    r = client.put(f"/api/targets/{tid}/slices/{sid}", json={"allocation_value": 75})
    assert r.status_code == 200
    assert r.json()["allocation_value"] == 75


def test_delete_slice(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1")
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 1000,
        "slices": [{"account_id": "acc1", "allocation_kind": "amount", "allocation_value": 500}]
    })
    tid = cr.json()["id"]
    sid = cr.json()["slices"][0]["id"]
    r = client.delete(f"/api/targets/{tid}/slices/{sid}")
    assert r.status_code == 204
    g = client.get(f"/api/targets/{tid}").json()
    assert len(g["slices"]) == 0


def test_progression_asset(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=2500)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression")
    assert r.status_code == 200
    body = r.json()
    assert body["target_id"] == tid
    assert body["target_amount"] == 5000
    assert body["current_value"] == 2500
    assert body["progress_pct"] == 50.0


def test_progression_bucket_with_override(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=10000)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "bucket", "target_amount": 8000,
        "rate_override": 200,
        "slices": [{"account_id": "acc1", "allocation_kind": "percent", "allocation_value": 30}]
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression")
    body = r.json()
    assert body["current_value"] == 3000.0
    assert body["rate"] == 200.0
    assert body["rate_source"] == "override"
    assert body["eta_status"] == "ok"
    assert abs(body["eta_months"] - 25.0) < 0.1


def test_progression_reached(client):
    user_id = _setup(client)
    _seed_account(user_id, "acc1", value=10000)
    cr = client.post("/api/targets", json={
        "name": "T", "type": "asset", "target_amount": 5000,
        "asset_account_id": "acc1", "asset_symbol": "VWCE", "slices": []
    })
    tid = cr.json()["id"]
    r = client.get(f"/api/targets/{tid}/progression").json()
    assert r["eta_status"] == "reached"
    assert r["eta_months"] is None
