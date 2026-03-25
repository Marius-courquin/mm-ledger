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

Index("idx_snapshots_account_date", balance_snapshots.c.account_id, balance_snapshots.c.date)
Index("idx_transactions_account_date", transactions.c.account_id, transactions.c.date)
Index("idx_performance_connector_period", performance.c.connector_id, performance.c.period_start)
