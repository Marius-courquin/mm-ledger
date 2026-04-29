from src.db.engine import create_engine_and_tables
from src.db.models import accounts, connectors, account_classification
from sqlalchemy import insert
from src.services.account_categorization import categorize_accounts


def _seed(tmp_path, accs, overrides=None):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        seen_connectors = set()
        for acc_id, conn_type in accs:
            if conn_type not in seen_connectors:
                conn.execute(insert(connectors).values(id=f"c_{conn_type}", type=conn_type))
                seen_connectors.add(conn_type)
            conn.execute(insert(accounts).values(id=acc_id, connector_id=f"c_{conn_type}", name=acc_id, type="x"))
        for acc_id, cat in (overrides or []):
            conn.execute(insert(account_classification).values(account_id=acc_id, category=cat))
    return engine


def test_categorize_default(tmp_path):
    engine = _seed(tmp_path, [
        ("livret_a", "woob_bank"),
        ("cto_tr", "trade_republic"),
        ("ibkr_acc", "ibkr"),
        ("nordigen_acc", "banking"),
    ])
    cats = categorize_accounts(engine)
    by_id = {c["account_id"]: c for c in cats}
    assert by_id["livret_a"]["category"] == "cash"
    assert by_id["livret_a"]["auto"] is True
    assert by_id["nordigen_acc"]["category"] == "cash"
    assert by_id["cto_tr"]["category"] == "market"
    assert by_id["ibkr_acc"]["category"] == "market"


def test_categorize_with_override(tmp_path):
    engine = _seed(tmp_path,
        [("cto_tr", "trade_republic")],
        overrides=[("cto_tr", "cash")],
    )
    cats = categorize_accounts(engine)
    by_id = {c["account_id"]: c for c in cats}
    assert by_id["cto_tr"]["category"] == "cash"
    assert by_id["cto_tr"]["auto"] is False


def test_categorize_unknown_connector(tmp_path):
    """Connecteur inconnu → market par défaut, auto=True."""
    engine = _seed(tmp_path, [("acc", "future_broker")])
    cats = categorize_accounts(engine)
    assert cats[0]["category"] == "market"
    assert cats[0]["auto"] is True
