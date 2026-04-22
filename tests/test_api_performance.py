from sqlalchemy import insert

from src.api import deps
from src.db.models import portfolio_history_daily


def _setup_admin(client):
    """Create admin + auto-login via cookie. Returns user_id."""
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    assert r.status_code == 201
    return r.json()["user"]["id"]


def _seed_history(user_id):
    engine = deps.get_ledger(user_id)
    rows = [
        {"connector_id": "ibkr", "account_id": "U1", "date": "2026-04-20",
         "total_value": 1000, "cash": 1000, "positions_value": 0,
         "cash_flow_external": 1000, "currency": "EUR"},
        {"connector_id": "ibkr", "account_id": "U1", "date": "2026-04-21",
         "total_value": 1050, "cash": 1000, "positions_value": 50,
         "cash_flow_external": 0, "currency": "EUR"},
        {"connector_id": "tr", "account_id": "ST1", "date": "2026-04-21",
         "total_value": 2000, "cash": 0, "positions_value": 2000,
         "cash_flow_external": 0, "currency": "EUR"},
    ]
    with engine.begin() as conn:
        for r in rows:
            conn.execute(insert(portfolio_history_daily).values(**r))


def test_history_aggregated(client):
    user_id = _setup_admin(client)
    _seed_history(user_id)
    r = client.get("/api/performance/history?period=All")
    assert r.status_code == 200
    data = r.json()
    assert "series" in data
    # 2 dates uniques dans le fixture
    assert len(data["series"]) == 2
    # Jour 2 : total = 1050 (ibkr) + 2000 (tr) = 3050
    last = data["series"][-1]
    assert last["value"] == 3050


def test_history_filtered_by_connector(client):
    user_id = _setup_admin(client)
    _seed_history(user_id)
    r = client.get("/api/performance/history?connector_id=ibkr&period=All")
    assert r.status_code == 200
    data = r.json()
    assert len(data["series"]) == 2
    assert data["series"][-1]["value"] == 1050


def test_history_filtered_by_account(client):
    user_id = _setup_admin(client)
    _seed_history(user_id)
    r = client.get("/api/performance/history?account_id=ST1&period=All")
    assert r.status_code == 200
    data = r.json()
    assert len(data["series"]) == 1
    assert data["series"][0]["value"] == 2000
