from pathlib import Path
from typing import Tuple
from git import Repo
import os
from datetime import datetime
import git
from git import Repo
import logging
from typing import Union
from pathlib import Path
import time
from datetime import timedelta
from gitchunk.task import Task

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%d-%m-%Y %I:%M:%S %p",
    level=logging.INFO,
    encoding="utf-8",
    handlers=[
        logging.FileHandler("gitchunk.log"),  # Log a archivo
        logging.StreamHandler(),  # Log a consola
    ],
)

logger = logging.getLogger(__name__)


def obtener_archivos(folder: Path, max_tamaño_archivo_mb):
    logger.debug(f"Buscando archivos en: {folder}")
    if isinstance(folder, str):
        folder = Path(folder)

    archivos_validos = []
    archivos_invalidos = []

    for root, dirs, files in os.walk(folder, topdown=True):
        if ".git" in dirs:
            dirs.remove(".git")
            logger.debug(f"Excluyendo directorio .git en: {root}")
        for file in files:
            path = Path(root) / file
            tamaño_mb = path.stat().st_size
            if tamaño_mb <= max_tamaño_archivo_mb:
                archivos_validos.append((path, tamaño_mb))
                logger.debug(f"Archivo válido: {path} ({tamaño_mb:.2f} MB)")
            else:
                archivos_invalidos.append((path, tamaño_mb))
                logger.warning(
                    f"Archivo inválido (excede el tamaño): {path} ({tamaño_mb:.2f} MB)"
                )
    logger.info(
        f"Encontrados {len(archivos_validos)} archivos válidos y {len(archivos_invalidos)} archivos inválidos."
    )
    return archivos_validos, archivos_invalidos


def agrupar_por_lotes(archivos, max_tamaño_lote_mb):
    lotes = []
    lote_actual = []
    tamaño_actual = 0

    for archivo, size, status in archivos:
        if status == "invalido":
            continue
        if tamaño_actual + size > max_tamaño_lote_mb:
            lotes.append(lote_actual)
            lote_actual = []
            tamaño_actual = 0
        lote_actual.append((archivo, size, status))
        tamaño_actual += size

    if lote_actual:
        lotes.append(lote_actual)

    return lotes


def add_files(lote, repo: Repo):
    for archivo, size, status in lote:
        if status == "eliminado":
            logger.debug("Eliminando archivo: %s (%s)", archivo, status)
            repo.index.remove(archivo)
        else:
            logger.debug("Agregando archivo: %s (%s)", archivo, status)
            repo.index.add(archivo)


def inicializar_git(folder: Path) -> Repo:
    if isinstance(folder, str):
        folder = Path(folder)

    if not (folder / ".git").exists():
        repo = git.Repo.init(folder)
        return repo
    else:
        return git.Repo((folder / ".git"))


def obtener_estado_archivo(repo, archivo):
    """
    Determina si un archivo específico es nuevo, modificado o sin cambios en un repositorio Git.

    Args:
        repo: Objeto del repositorio Git.
        archivo: Ruta al archivo relativo al repositorio.

    Returns:
        str: 'nuevo', 'modificado' o 'sin_cambios'
    """
    # Verificar si el archivo es nuevo (no está rastreado)
    folder = Path(repo.working_dir)
    file_as_posix = archivo.relative_to(folder).as_posix()
    if file_as_posix in repo.untracked_files:
        return "nuevo"

    # Verificar si el archivo está modificado
    for diff_item in repo.index.diff(None):
        if diff_item.a_path == file_as_posix:
            return "modificado"

    return "sin_cambios"


def check_git_folder(folder: Union[Path, str]) -> bool:
    """
    Comprueba si una subcarpeta contiene una .git.

    Args:
        folder (Path): Carpeta raíz a buscar.

    Returns:
        bool: Verdadero si se encuentra una carpeta .git, falso en caso contrario.
    """
    if isinstance(folder, str):
        folder = Path(folder)

    for root, dirs, files in os.walk(folder, topdown=True):
        if ".git" in dirs and root != str(folder):
            return True
    return False


def instance_files(repo, max_tamaño_archivo_mb):
    """
    Dado un repositorio Git y un tamaño máximo de archivo en MB,
    devuelve tres listas: archivos nuevos, archivos modificados y archivos inválidos.
    Un archivo es inválido si su tamaño es mayor al especificado.

    Args:
        repo: Objeto del repositorio Git.
        max_tamaño_archivo_mb: Tamaño máximo permitido para un archivo en MB.

    Returns:
        tuple: Tres listas de tuplas (ruta del archivo Path, tamaño en MB).
    """

    if check_git_folder(repo.working_dir):
        # repo.untracked_files no devuelve los archivos de una subcarpeta si esta tiene una carpeta .git
        raise ValueError(
            "La carpeta de trabajo contiene una carpeta .git. No se puede continuar."
        )

    archivos_nuevos = []
    archivos_modificados = []
    archvivos_invalidos = []
    folder = Path(repo.working_dir)
    for path_string in repo.untracked_files:
        path = folder / path_string
        file_size = path.stat().st_size
        if file_size <= max_tamaño_archivo_mb:
            archivos_nuevos.append((path, file_size))
        else:
            archvivos_invalidos.append(path)
    for diff_item in repo.index.diff(None):
        # change_type = diff_item.change_type.lower()
        # if change_type == "d":
        #     continue
        path = folder / diff_item.a_path
        file_size = path.stat().st_size
        if file_size <= max_tamaño_archivo_mb:
            archivos_modificados.append((path, file_size))
        else:
            archvivos_invalidos.append(path)
    return archivos_nuevos, archivos_modificados, archvivos_invalidos


def sleep_progress(seconds):
    minutes = int(timedelta(seconds=seconds).total_seconds() // 60)

    logger.info(f"Esperando {minutes} minutos antes de continuar...")
    count = 0
    for i in range(int(seconds), 0, -1):
        time.sleep(1)
        count += 1
        if count % 60 == 0:
            minutes -= 1
            logger.info(f"Esperando {minutes} minutos antes de continuar...")


def tiene_commits(repo: Repo) -> bool:
    return bool(list(repo.iter_commits()))


def reset_repo(repo: Repo):
    if tiene_commits(repo):
        logger.info("Reseteando archivos añadidos al índice...")
        repo.git.reset()
    else:
        logger.info("El repositorio no tiene commits previos. Omitiendo reset.")


def get_files(repo: Repo, max_tamaño_archivo_mb: int) -> set[Tuple[Path, int, str]]:
    """
    Dado un repositorio Git y un tamaño máximo de archivo en MB,
    devuelve tres listas: archivos nuevos, archivos modificados y archivos inválidos.
    Un archivo es inválido si su tamaño es mayor al especificado.

    Args:
        repo: Objeto del repositorio Git.
        max_tamaño_archivo_mb: Tamaño máximo permitido para un archivo en MB.

    Returns:
        tuple: Tres listas de tuplas (ruta del archivo Path, tamaño en MB).
    """

    if check_git_folder(repo.working_dir):
        # repo.untracked_files no devuelve los archivos de una subcarpeta si esta tiene una carpeta .git
        raise ValueError(
            "La carpeta de trabajo contiene una carpeta .git. No se puede continuar."
        )

    change_types = {
        "D": "eliminado",
        "M": "modificado",
        "T": "cambió el tipo de archivo",
        "R": "renombrado",
        "C": "copiado",
        "A": "nuevo",
    }
    files = set()
    folder = Path(repo.working_dir)
    reset_repo(repo)
    for path_string in repo.untracked_files:
        path = folder / path_string
        file_size = path.stat().st_size
        if file_size <= max_tamaño_archivo_mb:
            files.add((path, file_size, "nuevo"))
        else:
            files.add((path, file_size, "invalido"))

    # compara el working directory con el último commit
    for item in repo.index.diff(None):
        files.add(
            (folder / item.a_path, item.a_blob.size, change_types[item.change_type])
        )
    return files


def add_tag(repo: Repo, tag):
    if tag:
        if not tag in repo.tags:
            logger.info(f"Creando tag: {tag}")
            try:
                repo.create_tag(tag)
                logger.info(f"Tag creado exitosamente.")
            except git.GitCommandError as e:
                logger.error(f"Error al crear el tag: {e}")


def add_remote(repo: Repo, command_remote: str, remote_name: str, local_dir: Path):

    if command_remote:
        try:
            if repo.remote(remote_name):
                url = command_remote.split()[-1]
                origin_urls = list(repo.remote(remote_name).urls)
                if url not in origin_urls:
                    logger.info(f"Actualizando URL del remoto {remote_name}...")
                    config_lock_path = local_dir / ".git" / "config.lock"
                    if config_lock_path.exists():
                        config_lock_path.unlink()
                    repo.remote(remote_name).set_url(url)
        except git.GitCommandError as e:
            logger.error(f"Error al ejecutar el comando remoto: {e}")
        except ValueError:
            repo.git.execute(command_remote)
            logger.info(f"Comando ejecutado: {command_remote}")


def push_tags(repo, tag, remote_name):
    if tag:
        logger.info(f"Subiendo todas las etiquetas a {remote_name}...")
        repo.git.push(remote_name, "--tags")


def push_commits(repo, remote_name, branch_name):
    if not repo.remote(remote_name):
        logger.info(f"Remoto {remote_name} no encontrado.")
        exit()

    rama_name = branch_name
    rama_remota = f"{remote_name}/{rama_name}"

    if len(repo.remotes[remote_name].refs) > 0:
        commits_pendientes = list(repo.iter_commits(f"{rama_remota}..{rama_name}"))
    else:
        commits_pendientes = list(repo.iter_commits(f"{rama_name}"))
    logger.info(f"Hay {len(commits_pendientes)} commits pendientes para subir.")

    for index, commit in enumerate(commits_pendientes[::-1], start=1):
        commit_hash = commit.hexsha
        message = commit.message
        date = commit.authored_datetime.strftime("%d-%m-%Y %I:%M:%S %p")
        author = commit.author.name
        logger.info(f"Subiendo commit {commit_hash} ({date}) de {author}: {message}")

        refspec = f"{commit_hash}:refs/heads/{rama_name}"
        try:
            r = repo.git.push(remote_name, refspec, "--force-with-lease")
            logger.info(f"Push exitoso del commit {commit_hash} a {rama_name}.")
        except git.GitCommandError as e:
            logger.error(f"Error al hacer push del commit {commit_hash}: {e}")
            exit()
        except Exception as e:
            logger.exception(f"Error inesperado durante el push: {e}")

        if index < len(commits_pendientes):
            sleep_progress(timedelta(minutes=5).total_seconds())
