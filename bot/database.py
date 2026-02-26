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
    Persistance du capital réel et des positions ouvertes.
    Une seule row (id=1) mise à jour à chaque changement.
    Permet au RiskManager de retrouver son état exact après redémarrage.
    """
    __tablename__ = "portfolio_snapshot"

    id = Column(Integer, primary_key=True, default=1)
    total_capital = Column(Float, default=500.0)
    peak_capital = Column(Float, default=500.0)
    daily_pnl = Column(Float, default=0.0)
    daily_reset_date = Column(String(10), default="")
    open_positions_csv = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow)


# Colonnes à ajouter si absentes (migration safe sur base existante)
_SAFE_MIGRATIONS = [
    ("tracked_wallets",    "consecutive_losses",  "INTEGER NOT NULL DEFAULT 0"),
    ("tracked_wallets",    "entry_timing_score",  "REAL NOT NULL DEFAULT 0.5"),
    ("portfolio_snapshot", "open_positions_csv",  "TEXT NOT NULL DEFAULT ''"),
    ("copied_trades",      "pnl_usdc",            "REAL"),
]


def _run_safe_migrations(conn, is_postgres: bool) -> None:
    """
    FIX P1: exécute les migrations ALTER TABLE sur SQLite ET PostgreSQL.
    PostgreSQL utilise DO $$ block (compatible toutes versions >= 8.0).
    SQLite utilise 'ADD COLUMN' avec catch de 'duplicate column'.
    """
    for table, column, definition in _SAFE_MIGRATIONS:
        try:
            if is_postgres:
                # FIX P1: DO $$ block compatible PG toutes versions (pas IF NOT EXISTS)
                conn.execute(text(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='{table}' AND column_name='{column}'
                        ) THEN
                            ALTER TABLE {table} ADD COLUMN {column} {definition};
                        END IF;
                    END $$;
                """))
                conn.commit()
                logger.debug(f"[DB] PG migration OK: {table}.{column}")
            else:
                # SQLite: pas de IF NOT EXISTS, on catch 'duplicate column'
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                ))
                conn.commit()
                logger.info(f"[DB] Migration: {table}.{column} ajoutée")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                pass  # colonne déjà présente — normal
            else:
                logger.warning(f"[DB] Migration {table}.{column} inattendue: {e}")


def init_db() -> None:
    """
    Crée toutes les tables si elles n'existent pas.
    Applique aussi les migrations ALTER TABLE sécurisées.
    """
    Base.metadata.create_all(bind=engine)

    # Détection du dialecte
    db_url = settings.database_url.lower()
    is_postgres = "postgresql" in db_url or "postgres" in db_url

    with engine.connect() as conn:
        _run_safe_migrations(conn, is_postgres=is_postgres)

    # Seed de la row portfolio_snapshot si absente
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
