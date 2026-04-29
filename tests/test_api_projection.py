from sqlalchemy import insert
from src.db.models import accounts, connectors, balance_snapshots, loans
from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def _seed_accounts(user_id):
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="bp", type="woob_bank"))
        conn.execute(insert(connectors).values(id="tr", type="trade_republic"))
        conn.execute(insert(accounts).values(id="livret", connector_id="bp", name="Livret", type="cash"))
        conn.execute(insert(accounts).values(id="cto", connector_id="tr", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="livret", date="2026-04-29", cash=5000, positions_value=0, total_value=5000, positions=[],
        ))
        conn.execute(insert(balance_snapshots).values(
            account_id="cto", date="2026-04-29", cash=200, positions_value=10000, total_value=10200, positions=[],
        ))


def test_get_settings_default(client):
    _setup(client)
    r = client.get("/api/projection/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["settings"]["cash_annual_rate"] == 0.02
    assert body["settings"]["market_annual_rate"] == 0.05
    assert body["settings"]["horizon_years"] == 10


def test_update_settings(client):
    _setup(client)
    r = client.put("/api/projection/settings", json={
        "cash_annual_rate": 0.03, "market_annual_rate": 0.07,
        "cash_monthly_contribution": 100, "market_monthly_contribution": 500,
        "horizon_years": 20
    })
    assert r.status_code == 200
    g = client.get("/api/projection/settings").json()
    assert g["settings"]["cash_annual_rate"] == 0.03
    assert g["settings"]["horizon_years"] == 20


def test_compute_projection(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    r = client.get("/api/projection/compute")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["starting_state"]["cash"] == 5000
    assert body["starting_state"]["market"] == 10200
    assert body["starting_state"]["loan_monthly"] == 0
    assert len(body["points"]) == 120


def test_compute_with_loan(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=10000,
            monthly_payment=300, total_months=36, start_date="2024-01-01"
        ))
    r = client.get("/api/projection/compute")
    body = r.json()
    assert body["starting_state"]["loan_monthly"] == 300


def test_account_override(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    # cto par défaut = market → on l'override en cash
    r = client.post("/api/projection/account-override", json={"account_id": "cto", "category": "cash"})
    assert r.status_code == 204
    s = client.get("/api/projection/settings").json()
    cls = {c["account_id"]: c for c in s["classifications"]}
    assert cls["cto"]["category"] == "cash"
    assert cls["cto"]["auto"] is False
    cmp = client.get("/api/projection/compute").json()
    assert cmp["starting_state"]["cash"] == 5000 + 10200
    assert cmp["starting_state"]["market"] == 0


def test_remove_override(client):
    user_id = _setup(client)
    _seed_accounts(user_id)
    client.post("/api/projection/account-override", json={"account_id": "cto", "category": "cash"})
    r = client.delete("/api/projection/account-override/cto")
    assert r.status_code == 204
    s = client.get("/api/projection/settings").json()
    cls = {c["account_id"]: c for c in s["classifications"]}
    assert cls["cto"]["category"] == "market"
    assert cls["cto"]["auto"] is True


def test_unauth(client):
    r = client.get("/api/projection/settings")
    assert r.status_code == 401
