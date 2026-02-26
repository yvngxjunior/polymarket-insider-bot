from datetime import datetime, date
from sqlalchemy import (
    create_engine, Column, String, Float, Boolean,
    Integer, DateTime, Text, ForeignKey, Enum as SAEnum, text
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker, Session
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import enum

from bot.config import get_settings
from bot.utils.logger import logger

settings = get_settings()

engine = create_engine(
    settings.database_url,
    poolclass=NullPool,
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class TradeStatus(enum.Enum):
    PENDING = "pending"
    EXECUTED = "executed"
    SKIPPED = "skipped"
    FAILED = "failed"


class TrackedWallet(Base):
    """Wallets insider détectés et suivis."""
    __tablename__ = "tracked_wallets"

    address = Column(String(42), primary_key=True)
    label = Column(String(100), nullable=True)
    win_rate = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    total_profit_usd = Column(Float, default=0.0)
    score = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    is_whale = Column(Boolean, default=False)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    consecutive_losses = Column(Integer, default=0)
    entry_timing_score = Column(Float, default=0.5)

    trades = relationship("CopiedTrade", back_populates="source_wallet")

    def __repr__(self):
        return f"<Wallet {self.address[:8]}... score={self.score:.2f} wr={self.win_rate:.0%}>"


class CopiedTrade(Base):
    """Historique des trades copiés."""
    __tablename__ = "copied_trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_wallet_address = Column(String(42), ForeignKey("tracked_wallets.address"))
    market_id = Column(String(100))
    market_question = Column(Text, nullable=True)
    token_id = Column(String(100))
    side = Column(String(4))
    amount_usdc = Column(Float)
    price = Column(Float)
    # FIX DB-2: pnl_usdc manquant — requis par performance.py pour le vrai P&L
    # Mis à jour par ExitManager à la clôture de la position (TP1/TP2/SL/RESOLVING)
    pnl_usdc = Column(Float, nullable=True, default=None)
    status = Column(SAEnum(TradeStatus), default=TradeStatus.PENDING)
    skip_reason = Column(String(200), nullable=True)
    tx_hash = Column(String(66), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)

    source_wallet = relationship("TrackedWallet", back_populates="trades")

    def __repr__(self):
        return f"<Trade {self.side} {self.amount_usdc}$ on {self.market_id[:12]}... [{self.status.value}]>"


class WalletPerformance(Base):
    """Snapshot quotidien de perf par wallet."""
    __tablename__ = "wallet_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    wallet_address = Column(String(42))
    date = Column(DateTime)
    win_rate = Column(Float)
    total_profit = Column(Float)
    trades_count = Column(Integer)
    score = Column(Float)


class PortfolioSnapshot(Base):
    """
    FIX #1 — Persistance du capital réel et des positions ouvertes.
    Une seule row (id=1) mise à jour à chaque changement.
    Permet au RiskManager de retrouver son état exact après redémarrage.
    """
    __tablename__ = "portfolio_snapshot"

    id = Column(Integer, primary_key=True, default=1)
    total_capital = Column(Float, default=500.0)
    peak_capital = Column(Float, default=500.0)
    daily_pnl = Column(Float, default=0.0)
    daily_reset_date = Column(String(10), default="")  # ISO date YYYY-MM-DD
    # FIX #2 — open_positions : CSV des token_ids ouverts
    open_positions_csv = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


# Colonnes à ajouter si absentes (migration safe sur base existante)
_SAFE_MIGRATIONS = [
    ("tracked_wallets",  "consecutive_losses", "INTEGER NOT NULL DEFAULT 0"),
    ("tracked_wallets",  "entry_timing_score", "REAL NOT NULL DEFAULT 0.5"),
    ("portfolio_snapshot", "open_positions_csv", "TEXT NOT NULL DEFAULT ''"),
    # FIX DB-2: pnl_usdc ajouté pour le vrai P&L dans performance.py
    ("copied_trades",    "pnl_usdc",           "REAL"),
]


def init_db() -> None:
    """
    Crée toutes les tables si elles n'existent pas.
    Applique aussi les migrations ALTER TABLE sécurisées.

    FIX DB-1 — Seed portfolio_snapshot row id=1 compatible SQLite + PostgreSQL.
    """
    Base.metadata.create_all(bind=engine)

    if "sqlite" in settings.database_url:
        with engine.connect() as conn:
            for table, column, definition in _SAFE_MIGRATIONS:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
                    conn.commit()
                    logger.info(f"[DB] Migration: {table}.{column} ajoutée")
                except Exception as e:
                    if "duplicate column" in str(e).lower():
                        pass
                    else:
                        logger.warning(f"[DB] Migration {table}.{column} inattendue: {e}")

    # FIX DB-1 — Seed de la row portfolio_snapshot si absente
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM portfolio_snapshot WHERE id=1")
        ).fetchone()
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO portfolio_snapshot "
                    "(id, total_capital, peak_capital, daily_pnl, "
                    "daily_reset_date, open_positions_csv, updated_at) "
                    "VALUES (1, 500.0, 500.0, 0.0, :today, '', :now)"
                ),
                {"today": today, "now": now},
            )
            conn.commit()
            logger.info("[DB] portfolio_snapshot row seeded (id=1).")

    logger.info("Database tables initialized.")


@contextmanager
def get_db() -> Session:
    """Context manager pour une session DB propre."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
