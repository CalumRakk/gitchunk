import json
import logging
import os
import sys
from os import getenv
from pathlib import Path
from typing import Dict, Optional, cast

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class Profile(BaseModel):
    name: str
    token: str
    created_at: str


class ConfigSchema(BaseModel):
    profiles: Dict[str, str] = {}  # nombre_perfil : token
    default_profile: Optional[str] = None


def get_user_config_dir(app_name: str = "gitchunk") -> Path:
    """Obtiene la ruta estándar de configuración según el SO."""
    if sys.platform.startswith("win"):
        return Path(cast(str, getenv("APPDATA"))) / app_name
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    else:
        # Linux / Unix
        return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / app_name


class ConfigManager:
    def __init__(self):
        self.config_dir = get_user_config_dir()
        self.config_file = self.config_dir / "config.json"
        self._ensure_dir()
        self.data: ConfigSchema = self._load()

    def _ensure_dir(self):
        """Crea el directorio de configuración si no existe."""
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> ConfigSchema:
        """Carga la configuración desde el JSON o crea una vacía."""
        if not self.config_file.exists():
            return ConfigSchema()

        try:
            content = self.config_file.read_text(encoding="utf-8")
            return ConfigSchema.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError):
            logger.warning("Archivo de configuración corrupto. Iniciando uno nuevo.")
            return ConfigSchema()

    def save(self):
        """Guarda el estado actual en el archivo JSON."""
        content = self.data.model_dump_json(indent=4)
        self.config_file.write_text(content, encoding="utf-8")

    def add_profile(self, name: str, token: str) -> bool:
        """
        Añade o actualiza un perfil.
        Si es el primero, lo establece como default automáticamente.
        """
        is_first = len(self.data.profiles) == 0
        self.data.profiles[name] = token

        if is_first or self.data.default_profile is None:
            self.data.default_profile = name

        self.save()
        return is_first

    def set_default(self, name: str):
        """Cambia el perfil por defecto."""
        if name not in self.data.profiles:
            raise ValueError(f"El perfil '{name}' no existe.")
        self.data.default_profile = name
        self.save()

    def get_token(self, profile_name: Optional[str] = None) -> str:
        """
        Obtiene el token.
        Si no se especifica nombre, usa el default.
        """
        target = profile_name or self.data.default_profile

        if not target:
            raise ValueError(
                "No hay un perfil seleccionado ni uno por defecto configurado."
            )

        if target not in self.data.profiles:
            raise ValueError(f"El perfil '{target}' no existe.")

        return self.data.profiles[target]

    def list_profiles(self) -> Dict[str, bool]:
        """Retorna un dict {nombre: es_default}."""
        return {
            name: (name == self.data.default_profile)
            for name in self.data.profiles.keys()
        }

    def remove_profile(self, name: str):
        if name in self.data.profiles:
            del self.data.profiles[name]
            if self.data.default_profile == name:
                self.data.default_profile = None
            self.save()
