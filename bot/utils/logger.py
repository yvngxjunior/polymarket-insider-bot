import os
import sys
from loguru import logger
from pathlib import Path

# FIX LOGGER-1: logger.remove(0) supprime uniquement le handler loguru par défaut
# (index 0), pas tous les handlers potentiellement ajoutés par d'autres modules.
# L'ancienne version utilisait logger.remove() sans argument = supprime TOUT.
logger.remove(0)

# FIX LOGGER-2: niveau console lit LOG_LEVEL depuis l'env (via settings)
# Avant: level="INFO" hardcodé — ignorait complètement la variable .env
# Import tardif pour éviter les imports circulaires (config.py -> logger.py)
_console_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Crée le dossier logs (après remove pour éviter les side-effects au module load)
try:
    Path("logs").mkdir(parents=True, exist_ok=True)
except PermissionError as e:
    # En CI ou environnement read-only, on continue sans logs fichier
    sys.stderr.write(f"[LOGGER] Cannot create logs dir: {e}\n")

# Console (coloré + lisible)
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=_console_level,
)

# Fichier rotatif journalier
try:
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="14 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level="DEBUG",
        encoding="utf-8",
    )

    # Fichier séparé pour les erreurs uniquement
    logger.add(
        "logs/errors.log",
        level="ERROR",
        rotation="100 MB",
        retention="30 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} | {message}\n{exception}",
        encoding="utf-8",
    )
except Exception as e:
    sys.stderr.write(f"[LOGGER] File handler setup failed: {e}\n")

__all__ = ["logger"]
