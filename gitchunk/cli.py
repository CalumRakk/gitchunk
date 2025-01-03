import os
from datetime import datetime
import git
from git import Repo
import logging

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


def convertir_a_mb(bytes):
    return bytes / (1024 * 1024)


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
            tamaño_mb = convertir_a_mb(path.stat().st_size)
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

    for archivo, tamaño in archivos:
        if tamaño_actual + tamaño > max_tamaño_lote_mb:
            lotes.append(lote_actual)
            lote_actual = []
            tamaño_actual = 0
        lote_actual.append(archivo)
        tamaño_actual += tamaño

    if lote_actual:
        lotes.append(lote_actual)

    return lotes


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


def instance_files(repo, max_tamaño_archivo_mb):
    archivos_nuevos = []
    archivos_modificados = []
    archvivos_invalidos = []
    folder = Path(repo.working_dir)
    for path_string in repo.untracked_files:
        path = folder / path_string
        file_size = convertir_a_mb(path.stat().st_size)
        if file_size <= max_tamaño_archivo_mb:
            archivos_nuevos.append((path, file_size))
        else:
            archvivos_invalidos.append(path)
    for diff_item in repo.index.diff(None):
        path = folder / diff_item.a_path
        file_size = convertir_a_mb(path.stat().st_size)
        if file_size <= max_tamaño_archivo_mb:
            archivos_modificados.append((path, file_size))
        else:
            archvivos_invalidos.append(path)
    return archivos_nuevos, archivos_modificados, archvivos_invalidos


def main():
    logger.info("Iniciando gitchunk...")
    for file in Path("tasks").glob("*.txt"):
        logger.info(f"Procesando archivo de configuración: {file}")
        try:
            config = Task.from_filepath(file)
        except FileNotFoundError as e:
            logger.error(f"Error al leer el archivo de configuración: {e}")
            continue

        FOLDER = config.local_dir
        MAX_FILE_SIZE_MB = config.max_file_size_mb
        MAX_BATCH_SIZE_MB = config.max_batch_size_mb
        AUTHOR = config.author
        REMOTE_NAME = config.remote_name
        BRANCH_NAME = config.branch_name
        logger.info(f"Configuración cargada: {config.__dict__}")

        try:
            repo = inicializar_git(FOLDER)
        except git.InvalidGitRepositoryError as e:
            logger.error(f"Error al inicializar/abrir el repositorio Git: {e}")
            continue
        except Exception as e:
            logger.exception(f"Error inesperado al inicializar el repositorio: {e}")
            continue

        archivos_nuevos, archivos_modificados, archvivos_invalidos = instance_files(
            repo, MAX_FILE_SIZE_MB
        )
        logger.info(
            f"Archivos nuevos: {len(archivos_nuevos)}, modificados: {len(archivos_modificados)}, inválidos: {len(archvivos_invalidos)}"
        )

        lotes = agrupar_por_lotes(archivos_nuevos, MAX_BATCH_SIZE_MB)
        logger.info(f"Se crearán {len(lotes)} lotes.")

        for i, lote in enumerate(lotes, start=1):
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            add_files = []
            for archivo in lote:
                status = obtener_estado_archivo(repo, archivo)
                if status in ["nuevo", "modificado"]:
                    add_files.append(archivo)
            message = f"{date} - Copia de archivos por lote ({i}/{len(lotes)}) ({len(lote)} archivos)"
            logger.info(f"Creando commit: {message}")
            try:
                repo.index.add(add_files)
                repo.index.commit(message, author=AUTHOR)
                logger.info(f"Commit creado exitosamente.")
            except Exception as e:
                logger.exception(f"Error al crear el commit: {e}")

        remoto = REMOTE_NAME
        rama_name = BRANCH_NAME
        rama_remota = f"{remoto}/{rama_name}"
        commits_pendientes = list(repo.iter_commits(f"{rama_remota}..{rama_name}"))
        logger.info(f"Hay {len(commits_pendientes)} commits pendientes para subir.")
        for commit in commits_pendientes[::-1]:
            commit_hash = commit.hexsha
            message = commit.message
            date = commit.authored_datetime.strftime("%Y-%m-%d %H:%M:%S")
            author = commit.author.name
            refspec = f"{commit_hash}:refs/heads/{rama_name}"
            try:
                repo.git.push(remoto, refspec, "--force-with-lease")
                logger.info(f"Push exitoso del commit {commit_hash} a {rama_name}.")
            except git.GitCommandError as e:
                logger.error(f"Error al hacer push del commit {commit_hash}: {e}")
            except Exception as e:
                logger.exception(f"Error inesperado durante el push: {e}")

            time.sleep(timedelta(minutes=5).total_seconds())
    logger.info("Finalizando gitchunk.")


if __name__ == "__main__":
    main()
