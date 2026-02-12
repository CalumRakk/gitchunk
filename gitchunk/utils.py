import hashlib
import logging
import re
from pathlib import Path
from time import sleep

from .schemas import *

logger = logging.getLogger(__name__)


def normalize_windows_name(name: str) -> str:
    invalid_chars = r'[<>:"/\\|?*\x00-\x1F]'
    name = re.sub(invalid_chars, "_", name)
    name = name.rstrip(" .")
    if len(name) < 0:
        raise ValueError("Invalid name")
    return name


def sleep_progress(seconds: float):
    total = int(seconds)
    if total <= 0:
        return

    logger.info(
        f"Esperando {total // 60} minutos y {total % 60} segundos antes de continuar..."
    )

    for i in range(total, 0, -1):
        sleep(1)
        if i % 60 == 0:
            mins_left = i // 60
            logger.info(f"Faltan {mins_left} minutos...")
        elif i <= 10:  # Mostrar segundos finales
            logger.info(f"{i} segundos restantes...")


def create_md5sum_by_hashlib(path: Path):
    """
    Calcula el MD5 de un archivo. Si el archivo es grande (>100MB)
    """
    hash_md5 = hashlib.md5()

    print(f"[dim]Procesando firma digital (MD5): {path.name}...[/dim]")

    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(50 * 1024 * 1024), b""):
            hash_md5.update(chunk)

    return hash_md5.hexdigest()
