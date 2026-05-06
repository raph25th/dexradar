from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Token(TimestampMixin, Base):
    __tablename__ = "tokens"
    __table_args__ = (
        UniqueConstraint("chain_id", "address", name="uq_tokens_chain_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    pairs: Mapped[list["Pair"]] = relationship(
        back_populates="base_token",
        cascade="all, delete-orphan",
    )


class Pair(TimestampMixin, Base):
    __tablename__ = "pairs"
    __table_args__ = (
        UniqueConstraint("chain_id", "pair_address", name="uq_pairs_chain_pair_address"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dex_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pair_address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    base_token_id: Mapped[int] = mapped_column(
        ForeignKey("tokens.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quote_token_symbol: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dexscreener_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pair_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    base_token: Mapped[Token] = relationship(back_populates="pairs")
    snapshots: Mapped[list["PairSnapshot"]] = relationship(
        back_populates="pair",
        cascade="all, delete-orphan",
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="pair",
        cascade="all, delete-orphan",
    )


class PairSnapshot(Base):
    __tablename__ = "pair_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_id: Mapped[int] = mapped_column(
        ForeignKey("pairs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_usd: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)
    liquidity_usd: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    fdv: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_5m: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_1h: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_6h: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    volume_24h: Mapped[Decimal | None] = mapped_column(Numeric(24, 2), nullable=True)
    txns_5m_buys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    txns_5m_sells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    txns_1h_buys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    txns_1h_sells: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_change_5m: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    price_change_1h: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    price_change_6h: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    price_change_24h: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pair: Mapped[Pair] = relationship(back_populates="snapshots")
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pair_id: Mapped[int] = mapped_column(
        ForeignKey("pairs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("pair_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    sent_to_telegram: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pair: Mapped[Pair] = relationship(back_populates="alerts")
    snapshot: Mapped[PairSnapshot] = relationship(back_populates="alerts")
