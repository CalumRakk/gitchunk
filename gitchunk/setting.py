from pathlib import Path
from typing import Optional, Union

from pydantic import ValidationError
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    host: Optional[str] = None
    acces_token: Optional[str] = None
    file: Path
    branch_name: str = "master"
    remote_name: str = "origin"


def get_settings(env_path: Union[Path, str] = ".env") -> Settings:
    """
    Carga configuración desde un archivo .env

    La utilidad principal es ocultar el falso positivo de pylance al advertir que faltan argumentos que van a ser cargados desde el archivo .env
    Ver https://github.com/pydantic/pydantic/issues/3753
    """
    env_path = Path(env_path) if isinstance(env_path, str) else env_path
    try:
        if env_path.exists():
            settings = Settings(_env_file=env_path)  # type: ignore
            return settings
        raise FileNotFoundError(f"El archivo de configuración {env_path} no existe.")
    except ValidationError as e:
        print("Error en configuración:", e)
        raise
