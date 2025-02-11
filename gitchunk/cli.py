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


def main():
    logger.info("Iniciando gitchunk...")

    # loads configs
    tasks = []
    for file in Path("tasks").rglob("*.txt"):
        logger.info(f"Procesando archivo de configuración: {file}")
        content = file.read_text()
        configs = Task._parsed_content(content)
        tasks.extend([Task.from_dict(config) for config in configs])

    for config in tasks:
        logger.info(f"Procesando tarea: {config}")
        FOLDER = config.local_dir
        MAX_FILE_SIZE_MB = config.max_file_size_bytes
        MAX_BATCH_SIZE_MB = config.max_batch_size_bytes
        AUTHOR = config.author
        REMOTE_NAME = config.remote_name
        BRANCH_NAME = config.branch_name
        COMMITTER = config.committer
        COMMAND_REMOTE = config.command_remote
        TAG = config.tag
        logger.info(f"Configuración cargada: {config.__dict__}")

        if not FOLDER.exists():
            logger.error(f"La carpeta de trabajo no existe: {FOLDER}")
            continue

        try:
            repo = inicializar_git(FOLDER)
        except git.InvalidGitRepositoryError as e:
            logger.error(f"Error al inicializar/abrir el repositorio Git: {e}")
            continue
        except Exception as e:
            logger.exception(f"Error inesperado al inicializar el repositorio: {e}")
            continue

        logger.info("Reseteando archivos añadidos al índice...")

        if not "No commits yet" in repo.git.execute("git status"):
            repo.index.reset()

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
                if len(add_files) > 200:
                    logger.info(
                        f"Creando un commit de {len(add_files)} archivos, esto podrá tardar..."
                    )

                repo.index.add(add_files)
                repo.index.commit(message, author=AUTHOR, committer=COMMITTER)
                logger.info(f"Commit creado exitosamente.")
            except Exception as e:
                logger.exception(f"Error al crear el commit: {e}")
        if TAG:
            if not TAG in repo.tags:
                logger.info(f"Creando tag: {TAG}")
                try:
                    repo.create_tag(TAG)
                    logger.info(f"Tag creado exitosamente.")
                except git.GitCommandError as e:
                    logger.error(f"Error al crear el tag: {e}")

        if COMMAND_REMOTE:
            try:
                if repo.remote(REMOTE_NAME):
                    url = COMMAND_REMOTE.split()[-1]
                    origin_urls = list(repo.remote(REMOTE_NAME).urls)
                    if url not in origin_urls:
                        logger.info(f"Actualizando URL del remoto {REMOTE_NAME}...")
                        config_lock_path = FOLDER / ".git" / "config.lock"
                        if config_lock_path.exists():
                            config_lock_path.unlink()
                        repo.remote(REMOTE_NAME).set_url(url)
            except git.GitCommandError as e:
                logger.error(f"Error al ejecutar el comando remoto: {e}")
            except ValueError:
                repo.git.execute(COMMAND_REMOTE)
                logger.info(f"Comando ejecutado: {COMMAND_REMOTE}")

        remoto = REMOTE_NAME
        rama_name = BRANCH_NAME
        rama_remota = f"{remoto}/{rama_name}"
        if not repo.remote(remoto):
            logger.info(f"Remoto {remoto} no encontrado. Agregando...")
            exit()

        if len(repo.remotes[remoto].refs) > 0:
            commits_pendientes = list(repo.iter_commits(f"{rama_remota}..{rama_name}"))
        else:
            commits_pendientes = list(repo.iter_commits(f"{rama_name}"))

        logger.info(f"Hay {len(commits_pendientes)} commits pendientes para subir.")

        for index, commit in enumerate(commits_pendientes[::-1], start=1):
            commit_hash = commit.hexsha
            message = commit.message
            date = commit.authored_datetime.strftime("%d-%m-%Y %I:%M:%S %p")
            author = commit.author.name
            logger.info(
                f"Subiendo commit {commit_hash} ({date}) de {author}: {message}"
            )

            refspec = f"{commit_hash}:refs/heads/{rama_name}"
            try:
                r = repo.git.push(remoto, refspec, "--force-with-lease")
                logger.info(f"Push exitoso del commit {commit_hash} a {rama_name}.")
            except git.GitCommandError as e:
                logger.error(f"Error al hacer push del commit {commit_hash}: {e}")
                exit()
            except Exception as e:
                logger.exception(f"Error inesperado durante el push: {e}")

            if index < len(commits_pendientes):
                sleep_progress(timedelta(minutes=5).total_seconds())
        if TAG:
            logger.info(f"Subiendo todas las etiquetas a {remoto}...")
            repo.git.push(remoto, "--tags")

    logger.info("Finalizando gitchunk.")


if __name__ == "__main__":
    main()
