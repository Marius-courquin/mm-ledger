from sqlalchemy import insert
from src.db.models import connectors, accounts, balance_snapshots, transactions, performance
from src.api import deps


def _seed(client):
    client.post("/api/vault/setup", json={"password": "test"})
    client.post("/api/vault/unlock", json={"password": "test"})
    with deps.db_engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic", label="TR"))
        conn.execute(insert(accounts).values(id="tr_CTO", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="tr_CTO", date="2026-03-23", cash=100, positions_value=900, total_value=1000,
            positions=[{"symbol": "IWDA", "qty": 10, "price": 90, "value": 900}],
        ))
        conn.execute(insert(transactions).values(
            account_id="tr_CTO", date="2026-03-20", type="buy",
            label="IWDA", amount=-900, instrument="IE00B4L5Y983", quantity=10, price=90,
        ))
        conn.execute(insert(performance).values(
            connector_id="tr_1", period_start="2026-03-17", period_end="2026-03-23",
            total_value=1000, total_invested=900, pnl=100, pnl_pct=11.11,
        ))


def test_list_accounts(client):
    _seed(client)
    r = client.get("/api/accounts")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == "tr_CTO"


def test_get_snapshots(client):
    _seed(client)
    r = client.get("/api/snapshots?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["total_value"] == 1000


def test_get_transactions(client):
    _seed(client)
    r = client.get("/api/transactions?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["type"] == "buy"


def test_get_performance(client):
    _seed(client)
    r = client.get("/api/performance?from=2026-03-01&to=2026-03-31")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["pnl"] == 100
