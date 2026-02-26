#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration Script: data/ Directory Structure
============================================
Cree la structure optimisee data/ et migre la database existante.

Structure creee:
    data/
    |-- cache/         <- API response cache (Redis backup)
    |-- markets/       <- Market snapshots historiques
    |-- wallets/       <- Wallet profiles & stats
    |-- logs/          <- Logs rotatifs (optionnel)
    |-- snapshots/     <- Portfolio snapshots pour analytics
    +-- polyinsider.db <- SQLite database

Usage:
    python migrate_data_dir.py
"""
import os
import shutil
from pathlib import Path


def migrate():
    """
    Migre vers la structure data/ centralisee.
    Non-destructive: ne fait rien si deja migre.
    """
    print("=" * 60)
    print("  Migration: data/ Directory Structure")
    print("=" * 60)
    print()
    
    # -- Etape 1: Creer data/ -----------------------------------------------
    data_dirs = [
        "data",
        "data/cache",
        "data/markets",
        "data/wallets",
        "data/logs",
        "data/snapshots",
    ]
    
    for dir_path in data_dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"[OK] Created: {dir_path}/")
    
    print()
    
    # -- Etape 2: Migrer polyinsider.db -------------------------------------
    db_old = Path("polyinsider.db")
    db_new = Path("data/polyinsider.db")
    
    if db_old.exists():
        if db_new.exists():
            print(f"[WARN] Database already in data/ - skipping migration")
            print(f"       (Delete {db_old} manually if migration is complete)")
        else:
            shutil.move(str(db_old), str(db_new))
            print(f"[OK] Moved: polyinsider.db -> data/polyinsider.db")
    elif db_new.exists():
        print(f"[OK] Database already migrated: data/polyinsider.db")
    else:
        print(f"[INFO] No database found (will be created on first run)")
    
    print()
    
    # -- Etape 3: Creer README dans data/ -----------------------------------
    readme_path = Path("data/README.md")
    if not readme_path.exists():
        readme_content = """# data/ Directory Structure

Centralized data directory for better organization and performance.

## Structure

```
data/
|-- polyinsider.db     # SQLite database (trades, wallets, portfolio)
|-- cache/             # API response cache (Redis backup)
|-- markets/           # Market snapshots for historical analysis
|-- wallets/           # Wallet profiles & performance stats
|-- logs/              # Application logs (if file logging enabled)
+-- snapshots/         # Portfolio snapshots for analytics
```

## Cache Policy

- **Market Info**: 5 minutes TTL (markets change slowly)
- **Wallet Trades**: 10 seconds TTL (balance freshness vs rate-limits)
- **Wallet Profiles**: 5 minutes TTL (usernames stable)
- **Token Prices**: 5 seconds TTL (prices volatile)

## Backup

To backup all data:

```bash
tar -czf polyinsider-backup-$(date +%Y%m%d).tar.gz data/
```

## Restore

```bash
tar -xzf polyinsider-backup-YYYYMMDD.tar.gz
```
""".strip()
        # FIX: Specify UTF-8 encoding for Windows compatibility
        readme_path.write_text(readme_content, encoding='utf-8')
        print(f"[OK] Created: data/README.md")
    
    print()
    
    # -- Etape 4: Instructions post-migration -------------------------------
    print("-" * 60)
    print("Migration Complete!")
    print("-" * 60)
    print()
    print("Next steps:")
    print("  1. Update .env:")
    print("       DATABASE_URL=sqlite:///./data/polyinsider.db")
    print()
    print("  2. (Optional) Install Redis for persistent cache:")
    print("       docker run -d -p 6379:6379 redis:7-alpine")
    print("       REDIS_URL=redis://localhost:6379/0")
    print()
    print("  3. Restart the bot:")
    print("       python main.py")
    print()
    print("[OK] data/ structure ready!")
    print()


if __name__ == "__main__":
    migrate()
