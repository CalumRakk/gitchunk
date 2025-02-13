import re
import os
import time
import logging
from pathlib import Path
from typing import Union, Tuple
from datetime import timedelta

import requests
from git import Repo
import git

# El regex espera que haya una version en el nombre para ser capturado
regex_get_game_name = re.compile(r"^(.*?)(:?_?-?)(?:Release|Version|v|\d+\.\d+.*|pc)")
regex_get_version = re.compile(r"(\d+\.)+\d+")
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
    count = 50
    count_eliminados = 0
    count_agregados = 0
    for index, typle in enumerate(lote, start=1):
        archivo, size, status = typle
        if status == "eliminado":
            logger.debug("Eliminando archivo: %s (%s)", archivo, status)
            repo.index.remove(archivo)
            count_eliminados += 1
        else:
            logger.debug("Agregando archivo: %s (%s)", archivo, status)
            repo.index.add(archivo)
            count_agregados += 1

        if index % count == 0:
            logger.info(
                f"Iterado {index}/{len(lote)} archivos. Agregados {count_agregados} y eliminados {count_eliminados}"
            )

    logger.info(
        f"Iterado {len(lote)}/{len(lote)} archivos. Agregados {count_agregados} y eliminados {count_eliminados}"
    )


def inicializar_git(folder: Path) -> Repo:
    if isinstance(folder, str):
        folder = Path(folder)

    if not (folder / ".git").exists():
        repo = git.Repo.init(folder)
        return repo
    else:
        return git.Repo((folder / ".git"))


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
    if not "No commits yet" in repo.git.execute("git status"):
        return True
    return False


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


def get_game_name(filename):
    match = regex_get_game_name.match(filename)
    if match:
        return match.group(1)
    else:
        return None


def get_game_version(filename):
    match = regex_get_version.search(filename)
    if match:
        return match.group()
    else:
        return None


def load_access_token():
    with open("ACCESS_TOKEN", "r") as f:
        access_token = f.read().strip()
    return access_token


def creata_repostirotio(repo_name, description=None, private=True):
    access_token = load_access_token()
    GITHUB_API_URL = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"token {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "name": repo_name,
        "description": description,
        "private": private,
    }
    response = requests.post(GITHUB_API_URL, json=data, headers=headers)
    if response.status_code == 201:
        logger.info(f"Repositorio '{repo_name}' creado exitosamente!")
    else:
        logger.error(f"Error al crear el repositorio: {response.status_code}")
    return response.json()
