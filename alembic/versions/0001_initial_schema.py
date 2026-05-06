"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-27 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("address", sa.String(length=128), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tokens")),
        sa.UniqueConstraint("chain_id", "address", name="uq_tokens_chain_address"),
    )
    op.create_index(op.f("ix_tokens_address"), "tokens", ["address"], unique=False)
    op.create_index(op.f("ix_tokens_chain_id"), "tokens", ["chain_id"], unique=False)

    op.create_table(
        "pairs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain_id", sa.String(length=64), nullable=False),
        sa.Column("dex_id", sa.String(length=64), nullable=True),
        sa.Column("pair_address", sa.String(length=128), nullable=False),
        sa.Column("base_token_id", sa.Integer(), nullable=False),
        sa.Column("quote_token_symbol", sa.String(length=64), nullable=True),
        sa.Column("dexscreener_url", sa.Text(), nullable=True),
        sa.Column("pair_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["base_token_id"], ["tokens.id"], name=op.f("fk_pairs_base_token_id_tokens"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pairs")),
        sa.UniqueConstraint("chain_id", "pair_address", name="uq_pairs_chain_pair_address"),
    )
    op.create_index(op.f("ix_pairs_base_token_id"), "pairs", ["base_token_id"], unique=False)
    op.create_index(op.f("ix_pairs_chain_id"), "pairs", ["chain_id"], unique=False)
    op.create_index(op.f("ix_pairs_dex_id"), "pairs", ["dex_id"], unique=False)
    op.create_index(op.f("ix_pairs_pair_address"), "pairs", ["pair_address"], unique=False)

    op.create_table(
        "pair_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pair_id", sa.Integer(), nullable=False),
        sa.Column("price_usd", sa.Numeric(precision=36, scale=18), nullable=True),
        sa.Column("liquidity_usd", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("fdv", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("market_cap", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_5m", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_1h", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_6h", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_24h", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("txns_5m_buys", sa.Integer(), nullable=False),
        sa.Column("txns_5m_sells", sa.Integer(), nullable=False),
        sa.Column("txns_1h_buys", sa.Integer(), nullable=False),
        sa.Column("txns_1h_sells", sa.Integer(), nullable=False),
        sa.Column("price_change_5m", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_change_1h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_change_6h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_change_24h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pair_id"], ["pairs.id"], name=op.f("fk_pair_snapshots_pair_id_pairs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pair_snapshots")),
    )
    op.create_index(op.f("ix_pair_snapshots_pair_id"), "pair_snapshots", ["pair_id"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pair_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("sent_to_telegram", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pair_id"], ["pairs.id"], name=op.f("fk_alerts_pair_id_pairs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["pair_snapshots.id"], name=op.f("fk_alerts_snapshot_id_pair_snapshots"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
    )
    op.create_index(op.f("ix_alerts_level"), "alerts", ["level"], unique=False)
    op.create_index(op.f("ix_alerts_pair_id"), "alerts", ["pair_id"], unique=False)
    op.create_index(op.f("ix_alerts_score"), "alerts", ["score"], unique=False)
    op.create_index(op.f("ix_alerts_snapshot_id"), "alerts", ["snapshot_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_snapshot_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_score"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_pair_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_level"), table_name="alerts")
    op.drop_table("alerts")

    op.drop_index(op.f("ix_pair_snapshots_pair_id"), table_name="pair_snapshots")
    op.drop_table("pair_snapshots")

    op.drop_index(op.f("ix_pairs_pair_address"), table_name="pairs")
    op.drop_index(op.f("ix_pairs_dex_id"), table_name="pairs")
    op.drop_index(op.f("ix_pairs_chain_id"), table_name="pairs")
    op.drop_index(op.f("ix_pairs_base_token_id"), table_name="pairs")
    op.drop_table("pairs")

    op.drop_index(op.f("ix_tokens_chain_id"), table_name="tokens")
    op.drop_index(op.f("ix_tokens_address"), table_name="tokens")
    op.drop_table("tokens")
