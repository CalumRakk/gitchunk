import re
from typing import Optional

from packaging.version import parse as parse_version

REGEX_GAME_NAME = re.compile(
    r"^(.+?)[_ -]?(?:Release|Version|v|\d+\.\d+.*|pc)", re.IGNORECASE
)
REGEXVERSION = re.compile(r"(\d+\.)+\d+")


def get_game_name(filename: str) -> Optional[str]:
    match = REGEX_GAME_NAME.search(filename)
    return match.group(1) if match else None


def get_game_version(filename: str) -> Optional[str]:
    match = REGEXVERSION.search(filename)
    return match.group(0) if match else None


def is_version_older(current: str, latest: str) -> bool:
    """
    Retorna True si 'current' es una versión anterior a 'latest'.
    Usa packaging.version para manejar casos como 1.10 > 1.2
    """
    return parse_version(current) < parse_version(latest)
