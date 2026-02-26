"""
migrate.py — Migration one-shot pour les colonnes manquantes.

Utilisation:
    python migrate.py

Sécurité : chaque ALTER TABLE est guardé par un try/except
  — sans danger si les colonnes existent déjà (ex: base fraîche).
"""
import sqlite3
import sys
from pathlib import Path

from bot.config import get_settings

settings = get_settings()

# Extrait le chemin fichier depuis sqlite:///./bot.db  ou  sqlite:////abs/path/bot.db
db_url = settings.database_url
if not db_url.startswith("sqlite"):
    print("Ce script ne gère que SQLite. Pour PostgreSQL utilisez Alembic.")
    sys.exit(1)

db_path = db_url.replace("sqlite:///", "").replace("sqlite:////", "/")
if not Path(db_path).exists():
    print(f"Base non trouvée : {db_path}")
    print("Lance le bot une première fois pour créer les tables, puis relance migrate.py.")
    sys.exit(1)

MIGRATIONS = [
    # (table, colonne, définition SQL)
    ("tracked_wallets", "consecutive_losses", "INTEGER NOT NULL DEFAULT 0"),
    ("tracked_wallets", "entry_timing_score", "REAL NOT NULL DEFAULT 0.5"),
]

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for table, column, definition in MIGRATIONS:
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        print(f"  ✅ {table}.{column} ajoutée")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print(f"  ⏭️  {table}.{column} existe déjà — skipped")
        else:
            print(f"  ❌  {table}.{column} ERREUR: {e}")
            conn.close()
            sys.exit(1)

conn.commit()
conn.close()
print("\nMigration terminée. Tu peux relancer le bot.")
