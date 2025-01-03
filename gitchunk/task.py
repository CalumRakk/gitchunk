from pathlib import Path
import logging
from typing import Union
from git import Actor

logger = logging.getLogger(__name__)


def check_file(path: Union[Path, str]) -> Path:
    """Verifica si el archivo existe."""
    if isinstance(path, str):
        path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"El archivo {path} no existe.")
    return path


class Task:
    def __init__(
        self,
        task_path: Path,
        local_dir: Union[Path, str],
        remote_name: str = "origin",
        branch_name: str = "master",
        max_file_size_mb: int = 90,
        max_batch_size_mb: int = 300,
        author_name: str = None,
        author_email: str = None,
    ):
        self.task_path = check_file(task_path)
        self.local_dir = check_file(local_dir)
        self.remote_name = remote_name
        self.branch_name = branch_name
        self.max_file_size_mb = max_file_size_mb
        self.max_batch_size_mb = max_batch_size_mb
        self.author_name = author_name
        self.author_email = author_email
        self.author = Actor(name=author_name, email=author_email)

        logger.info(f"Configuración de la tarea: {self.__dict__}")

    @classmethod
    def from_filepath(cls, config_path: Path):
        logger.info(f"Leyendo archivo de configuración: {config_path}")

        if isinstance(config_path, str):
            config_path = Path(config_path)

        file = config_path.read_text()
        config = {}
        for line in file.splitlines():
            if not "=" in line or line == "" or line.startswith("#") or line == "\n":
                continue
            key, value = line.strip().split("=", 1)
            config[key.lower().strip()] = value.strip("\"' ")
            logger.info(f"Se ha asignado: {key.strip()}={value.strip()}")

        return cls(task_path=config_path, **config)
