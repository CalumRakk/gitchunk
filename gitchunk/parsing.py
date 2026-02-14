import re
from collections import defaultdict

from packaging.version import Version
from packaging.version import parse as parse_version


def strip_metadata(version_str: str) -> str:
    """Elimina metadatos de build (ej: +chunked) del string."""
    return re.sub(r"\+chunked", "", version_str)


def strip_platform(version_str: str) -> str:
    """Elimina el sufijo de plataforma (ej: -windows, -pc) si existe."""
    return re.sub(r"-[a-zA-Z0-9_]+(?=\+|$)", "", version_str)


def get_comparable_version(version_str: str) -> Version:
    """
    Convierte cualquier string (Ch.2, v1.0, 1.2.3) en un objeto Version comparable.
    """
    # Remueve plataforma o prefijo chunked
    clean = strip_metadata(version_str)
    clean = strip_platform(clean)

    # Extraer solo la parte numérica: "Ch.2.1" -> "2.1"
    match = re.search(r"(\d.*)", clean)
    if not match:
        raise ValueError(f"No se pudo extraer versión de '{version_str}'")

    clean_str = match.group(1)
    return parse_version(clean_str)


def grouped_by_platform(versions: list[str]):
    """Agrupa versiones por plataforma en el mismo orden en el llegan"""
    group = defaultdict(list)
    for v in versions:
        no_metadata = strip_metadata(v)
        if "-" in no_metadata:
            version_str, platform = no_metadata.rsplit("-", 1)
            group[platform].append(version_str)
    return group
