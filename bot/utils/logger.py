import sys
from loguru import logger
from pathlib import Path

# Crée le dossier logs
Path("logs").mkdir(exist_ok=True)

# Reset les handlers par défaut
logger.remove()

# Console (coloré + lisible)
logger.add(
    sys.stdout,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)

# Fichier rotatif journalier
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

__all__ = ["logger"]
