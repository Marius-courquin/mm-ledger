from src.performance import reconstruct_timeline, TxEvent, compute_twr, aggregate_timelines


def _tx(date: str, kind: str, **kw) -> TxEvent:
    return TxEvent(
        date=date, kind=kind,
        symbol=kw.get("symbol"),
        qty=kw.get("qty", 0.0),
        price=kw.get("price", 0.0),
        amount=kw.get("amount", 0.0),
    )


def test_reconstruct_empty():
    assert reconstruct_timeline([], {}, start_date="2026-01-01", end_date="2026-01-03") == [] or len(reconstruct_timeline([], {}, start_date="2026-01-01", end_date="2026-01-03")) == 3


def test_reconstruct_buy_only_single_day():
    txs = [_tx("2026-01-02", "buy", symbol="AMZN", qty=1.0, price=200.0, amount=-200.0)]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 195.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 210.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-03")
    assert len(timeline) == 3
    assert timeline[0]["date"] == "2026-01-01"
    assert timeline[0]["positions_value"] == 0.0
    assert timeline[0]["cash"] == 0.0
    assert timeline[1]["cash"] == -200.0
    assert timeline[1]["positions_value"] == 200.0
    assert timeline[2]["positions_value"] == 210.0
    assert timeline[2]["total_value"] == -200.0 + 210.0


def test_reconstruct_buy_then_sell():
    txs = [
        _tx("2026-01-02", "buy", symbol="AMZN", qty=2.0, price=200.0, amount=-400.0),
        _tx("2026-01-03", "sell", symbol="AMZN", qty=-1.0, price=250.0, amount=250.0),
    ]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 195.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 250.0},
        {"date": "2026-01-04", "close": 260.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-04")
    assert timeline[3]["positions_value"] == 260.0
    assert timeline[3]["cash"] == -150.0
    assert timeline[3]["total_value"] == 110.0


def test_reconstruct_external_deposit_tagged():
    txs = [_tx("2026-01-02", "deposit", amount=1000.0)]
    timeline = reconstruct_timeline(txs, {}, start_date="2026-01-01", end_date="2026-01-03")
    assert timeline[0]["cash_flow_external"] == 0.0
    assert timeline[1]["cash_flow_external"] == 1000.0
    assert timeline[1]["cash"] == 1000.0
    assert timeline[2]["cash"] == 1000.0
    assert timeline[2]["cash_flow_external"] == 0.0


def test_reconstruct_dividend_is_internal_gain():
    txs = [
        _tx("2026-01-02", "buy", symbol="AMZN", qty=1.0, price=200.0, amount=-200.0),
        _tx("2026-01-03", "dividend", symbol="AMZN", amount=5.0),
    ]
    prices = {"AMZN": [
        {"date": "2026-01-01", "close": 200.0},
        {"date": "2026-01-02", "close": 200.0},
        {"date": "2026-01-03", "close": 200.0},
    ]}
    timeline = reconstruct_timeline(txs, prices, start_date="2026-01-01", end_date="2026-01-03")
    assert timeline[2]["cash_flow_external"] == 0.0
    assert timeline[2]["cash"] == -195.0
    assert timeline[2]["total_value"] == 5.0


def test_twr_flat_no_move():
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert len(curve) == 2
    assert curve[0]["cum_pct"] == 0.0
    assert curve[1]["cum_pct"] == 0.0


def test_twr_simple_gain():
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 1100, "total_value": 1100, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert abs(curve[1]["cum_pct"] - 10.0) < 0.01


def test_twr_neutralizes_deposit():
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 1000, "total_value": 1000, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 500, "positions_value": 1000, "total_value": 1500, "cash_flow_external": 500},
        {"date": "2026-01-03", "cash": 500, "positions_value": 1150, "total_value": 1650, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert abs(curve[0]["cum_pct"] - 0.0) < 0.01
    assert abs(curve[1]["cum_pct"] - 0.0) < 0.01
    assert abs(curve[2]["cum_pct"] - 10.0) < 0.01


def test_twr_handles_zero_base():
    timeline = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 0, "total_value": 0, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 1000, "positions_value": 0, "total_value": 1000, "cash_flow_external": 1000},
        {"date": "2026-01-03", "cash": 0, "positions_value": 1100, "total_value": 1100, "cash_flow_external": 0},
    ]
    curve = compute_twr(timeline)
    assert curve[0]["cum_pct"] == 0.0
    assert curve[1]["cum_pct"] == 0.0
    assert abs(curve[2]["cum_pct"] - 10.0) < 0.01


def test_aggregate_two_connectors_sum_values():
    t1 = [
        {"date": "2026-01-01", "cash": 100, "positions_value": 500, "total_value": 600, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 100, "positions_value": 550, "total_value": 650, "cash_flow_external": 0},
    ]
    t2 = [
        {"date": "2026-01-01", "cash": 50, "positions_value": 300, "total_value": 350, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 50, "positions_value": 330, "total_value": 380, "cash_flow_external": 0},
    ]
    merged = aggregate_timelines([t1, t2])
    assert len(merged) == 2
    assert merged[0]["total_value"] == 950
    assert merged[1]["total_value"] == 1030


def test_aggregate_handles_different_date_ranges():
    t1 = [
        {"date": "2026-01-01", "cash": 0, "positions_value": 100, "total_value": 100, "cash_flow_external": 0},
        {"date": "2026-01-02", "cash": 0, "positions_value": 110, "total_value": 110, "cash_flow_external": 0},
    ]
    t2 = [
        {"date": "2026-01-02", "cash": 0, "positions_value": 200, "total_value": 200, "cash_flow_external": 200},
    ]
    merged = aggregate_timelines([t1, t2])
    assert [m["date"] for m in merged] == ["2026-01-01", "2026-01-02"]
    assert merged[0]["total_value"] == 100
    assert merged[1]["total_value"] == 310
    assert merged[1]["cash_flow_external"] == 200
