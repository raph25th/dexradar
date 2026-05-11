"""add candidate observations

Revision ID: 0002_candidate_observations
Revises: 0001_initial_schema
Create Date: 2026-05-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_candidate_observations"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pair_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("token_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("v2_status", sa.String(length=32), nullable=False),
        sa.Column("passed_profiles_json", sa.JSON(), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("avoid_reasons_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("liquidity_usd", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_1h", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("volume_24h", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("txns_1h_total", sa.Integer(), nullable=False),
        sa.Column("buy_ratio", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("volume_liquidity_ratio_1h", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("fdv_volume_ratio_1h", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("liquidity_fdv_ratio", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("fdv", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("market_cap", sa.Numeric(precision=24, scale=2), nullable=True),
        sa.Column("price_change_1h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_change_6h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("price_change_24h", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["pair_id"], ["pairs.id"], name=op.f("fk_candidate_observations_pair_id_pairs"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["pair_snapshots.id"], name=op.f("fk_candidate_observations_snapshot_id_pair_snapshots"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["token_id"], ["tokens.id"], name=op.f("fk_candidate_observations_token_id_tokens"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_observations")),
    )
    op.create_index(op.f("ix_candidate_observations_observed_at"), "candidate_observations", ["observed_at"], unique=False)
    op.create_index(op.f("ix_candidate_observations_pair_id"), "candidate_observations", ["pair_id"], unique=False)
    op.create_index(op.f("ix_candidate_observations_snapshot_id"), "candidate_observations", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_candidate_observations_token_id"), "candidate_observations", ["token_id"], unique=False)
    op.create_index(op.f("ix_candidate_observations_v2_status"), "candidate_observations", ["v2_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_candidate_observations_v2_status"), table_name="candidate_observations")
    op.drop_index(op.f("ix_candidate_observations_token_id"), table_name="candidate_observations")
    op.drop_index(op.f("ix_candidate_observations_snapshot_id"), table_name="candidate_observations")
    op.drop_index(op.f("ix_candidate_observations_pair_id"), table_name="candidate_observations")
    op.drop_index(op.f("ix_candidate_observations_observed_at"), table_name="candidate_observations")
    op.drop_table("candidate_observations")
