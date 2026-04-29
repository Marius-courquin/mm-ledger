from sqlalchemy import (
    MetaData, Table, Column, Integer, Text, REAL, JSON,
    ForeignKey, UniqueConstraint, Index
)

Real = REAL

metadata = MetaData()

connectors = Table(
    "connectors", metadata,
    Column("id", Text, primary_key=True),
    Column("type", Text, nullable=False),
    Column("label", Text),
    Column("config", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

accounts = Table(
    "accounts", metadata,
    Column("id", Text, primary_key=True),
    Column("connector_id", Text, ForeignKey("connectors.id"), nullable=False),
    Column("name", Text),
    Column("type", Text),
    Column("currency", Text, server_default="'EUR'"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

balance_snapshots = Table(
    "balance_snapshots", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Text, ForeignKey("accounts.id"), nullable=False),
    Column("date", Text, nullable=False),
    Column("cash", Real),
    Column("positions_value", Real),
    Column("total_value", Real),
    Column("currency", Text, server_default="'EUR'"),
    Column("positions", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
    UniqueConstraint("account_id", "date"),
)

transactions = Table(
    "transactions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", Text, ForeignKey("accounts.id"), nullable=False),
    Column("date", Text, nullable=False),
    Column("type", Text),
    Column("label", Text),
    Column("amount", Real),
    Column("currency", Text, server_default="'EUR'"),
    Column("instrument", Text),
    Column("quantity", Real),
    Column("price", Real),
    Column("raw", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

performance = Table(
    "performance", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("connector_id", Text, ForeignKey("connectors.id"), nullable=False),
    Column("period_start", Text, nullable=False),
    Column("period_end", Text, nullable=False),
    Column("total_value", Real),
    Column("total_invested", Real),
    Column("pnl", Real),
    Column("pnl_pct", Real),
    Column("breakdown", JSON),
    UniqueConstraint("connector_id", "period_start"),
)

net_worth_snapshots = Table(
    "net_worth_snapshots", metadata,
    Column("date", Text, primary_key=True),
    Column("total", Real),
    Column("bank_total", Real),
    Column("investments_total", Real),
    Column("breakdown", JSON),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

targets = Table(
    "targets", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("type", Text, nullable=False),  # 'asset' | 'bucket'
    Column("target_amount", Real, nullable=False),
    Column("asset_account_id", Text),  # NULL si type='bucket'
    Column("asset_symbol", Text),       # NULL si type='bucket'
    Column("rate_override", Real),      # NULL = auto
    Column("archived", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

target_slices = Table(
    "target_slices", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("target_id", Integer, ForeignKey("targets.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Text, nullable=False),
    Column("allocation_kind", Text, nullable=False),  # 'amount' | 'percent'
    Column("allocation_value", Real, nullable=False),
)

Index("idx_target_slices_target", target_slices.c.target_id)

Index("idx_snapshots_account_date", balance_snapshots.c.account_id, balance_snapshots.c.date)
Index("idx_transactions_account_date", transactions.c.account_id, transactions.c.date)
Index("idx_performance_connector_period", performance.c.connector_id, performance.c.period_start)

portfolio_history_daily = Table(
    "portfolio_history_daily", metadata,
    Column("connector_id", Text, nullable=False),
    Column("account_id", Text, nullable=False),
    Column("date", Text, nullable=False),
    Column("total_value", REAL, nullable=False),
    Column("cash", REAL, nullable=False),
    Column("positions_value", REAL, nullable=False),
    Column("cash_flow_external", REAL, nullable=False, default=0.0),
    Column("currency", Text, nullable=False, default="EUR"),
    UniqueConstraint("connector_id", "account_id", "date"),
)

Index(
    "idx_portfolio_history_connector_date",
    portfolio_history_daily.c.connector_id,
    portfolio_history_daily.c.date,
)

loans = Table(
    "loans", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("loan_type", Text, nullable=False),  # 'immo' | 'conso' | 'auto' | 'other'
    Column("initial_capital", Real, nullable=False),
    Column("monthly_payment", Real, nullable=False),
    Column("total_months", Integer, nullable=False),
    Column("start_date", Text, nullable=False),  # ISO YYYY-MM-DD
    Column("archived", Integer, nullable=False, server_default="0"),
    Column("created_at", Text, server_default="(datetime('now'))"),
)

projection_settings = Table(
    "projection_settings", metadata,
    Column("id", Integer, primary_key=True),  # toujours = 1
    Column("cash_annual_rate", Real, nullable=False, server_default="0.02"),
    Column("market_annual_rate", Real, nullable=False, server_default="0.05"),
    Column("cash_monthly_contribution", Real, nullable=False, server_default="0"),
    Column("market_monthly_contribution", Real, nullable=False, server_default="0"),
    Column("horizon_years", Integer, nullable=False, server_default="10"),
)

account_classification = Table(
    "account_classification", metadata,
    Column("account_id", Text, primary_key=True),
    Column("category", Text, nullable=False),  # 'cash' | 'market'
)
