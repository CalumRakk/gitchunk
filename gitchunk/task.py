from pathlib import Path
import logging
from typing import Union
from git import Actor

logger = logging.getLogger(__name__)


def check_file(
    path: Union[Path, str], nullable: bool = False, allow_nonexistent=False
) -> Path:
    """Verifica si el archivo existe."""
    if path is None and nullable is False:
        raise ValueError(f"Path debe ser proporcionado. nullable = {nullable}")
    if path is None and nullable is True:
        return None

    if isinstance(path, str):
        path = Path(path)
    if not path.exists() and not allow_nonexistent:
        raise FileNotFoundError(f"El archivo {path} no existe.")
    return path


class Task:
    def __init__(
        self,
        local_dir: Union[Path, str] = None,
        task_path: Path = None,
        remote_name: str = "origin",
        branch_name: str = "master",
        max_file_size_bytes: int = 90 * 1024 * 1024,
        max_batch_size_bytes: int = 300 * 1024 * 1024,
        author_name: str = None,
        author_email: str = None,
        command_remote: str = None,
        tag: str = None,
    ):
        self.task_path = check_file(task_path, nullable=True)
        self.local_dir = check_file(local_dir, nullable=False, allow_nonexistent=True)
        self.remote_name = remote_name
        self.branch_name = branch_name
        self.max_file_size_bytes = max_file_size_bytes
        self.max_batch_size_bytes = max_batch_size_bytes
        self.author_name = author_name
        self.author_email = author_email
        self.author = Actor(name=author_name, email=author_email)
        self.committer = Actor(name=author_name, email=author_email)
        self.command_remote = command_remote
        self.tag = tag

    @classmethod
    def from_filepath(cls, config_path: Path):
        logger.info(f"Leyendo archivo de configuración: {config_path}")

        if isinstance(config_path, str):
            config_path = Path(config_path)
        elif isinstance(config_path, None):
            logger.error("El path debe ser proporcionado.")
            raise ValueError("El path debe ser proporcionado.")

        if not config_path.exists():
            logger.error(f"El archivo de configuración {config_path} no existe.")
            raise FileNotFoundError(
                f"El archivo de configuración {config_path} no existe."
            )

        file = config_path.read_text()
        config = cls._parsed_content(file)[0]
        instance = cls(task_path=config_path, **config)
        logger.info(f"Instanciando tarea a partir de diccionario. {instance}")
        return instance

    @classmethod
    def from_dict(cls, config: dict):
        if not isinstance(config, dict):
            raise TypeError("El config debe ser un diccionario.")
        instance = cls(**config)
        logger.info(f"Instanciando tarea a partir de diccionario. {instance}")
        return instance

    @classmethod
    def _parsed_content(cls, content: str) -> list[dict]:
        logger.info("Parseando contenido.")

        if not isinstance(content, str):
            raise TypeError("El contenido debe ser una cadena de texto.")

        configs = []
        config = {}
        for line in content.splitlines():
            if line == "" or line.startswith("#") or line == "\n":
                continue
            elif line.startswith("---"):
                logger.debug("Se ha encontrado un bloque de configuración.")
                configs.append(config)
                config = dict()
                continue

            key, value = line.strip().split("=", 1)
            config[key.lower().strip()] = value.strip("\"' ")
            logger.debug(f"Se ha asignado: {key.strip()}={value.strip()}")
        configs.append(config)

        return configs

    def __str__(self):
        return f"Tarea para({self.local_dir})"
