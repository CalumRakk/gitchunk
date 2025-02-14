import logging
from datetime import datetime
from pathlib import Path
from gitchunk.task import Task
from gitchunk.utils import (
    inicializar_git,
    agrupar_por_lotes,
    push_commits,
    get_files,
    add_tag,
    add_remote,
    push_tags,
    add_files,
    get_game_name,
    get_game_version,
    creata_repostirotio,
)

logger = logging.getLogger(__name__)


def obtener_tarea_automatica(config: Task) -> Task | None:
    """Obtiene o crea una tarea automática basada en el nombre y versión del juego."""
    logger.info("Buscando tarea automática...")
    task_folder = Path("tasks") / "auto"
    game_name = get_game_name(config.local_dir.parent.name) or get_game_name(
        config.local_dir.name
    )
    game_version = get_game_version(config.local_dir.parent.name) or get_game_version(
        config.local_dir.name
    )

    if not game_name or not game_version:
        logger.error(
            "No se pudo obtener el nombre o la versión de la carpeta de trabajo."
        )
        return None

    task_path = task_folder / f"{game_name}.txt"
    if task_path.exists():
        logger.info(f"Usando tarea automática: {task_path}")
        config = Task.from_filepath(task_path)
        config.tag = game_version
    else:
        logger.info(f"Creando tarea automática: {task_path}")
        response = creata_repostirotio(repo_name=game_name, private=True)
        repo_full_name = response["full_name"]
        command_remote = (
            f"git remote add origin git@{config.host_github}:{repo_full_name}.git"
        )

        task_text = (
            f"local_dir={config.local_dir}\n"
            f"author_name={config.author_name}\n"
            f"author_email={config.author_email}\n"
            f"command_remote={command_remote}\n"
            f"tag={game_version}"
        )

        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(task_text)
        config = Task.from_filepath(task_path)

    return config


def procesar_commits(repo, lotes, config):
    """Realiza los commits en el repositorio según los lotes generados."""
    logger.info(f"Creando {len(lotes)} commits.")

    for index, lote in enumerate(lotes, start=1):
        logger.info(f"Creando commit {index}/{len(lotes)}...")

        if len(lote) > 200:
            logger.info("Más de 200 archivos en el lote, esto puede tardar...")

        add_files(lote, repo)
        message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Lote ({index}/{len(lotes)}) ({len(lote)} archivos)"
        repo.index.commit(message, author=config.author, committer=config.committer)

        logger.info("Commit creado exitosamente.")


def procesar_tarea(config: Task):
    """Procesa una tarea de GitChunk."""
    logger.info("-" * 75)

    if not config.local_dir.exists():
        logger.error(f"La carpeta de trabajo no existe: {config.local_dir}")
        return

    if config.command_remote and config.command_remote.lower() == "auto":
        config = obtener_tarea_automatica(config)
        if not config:
            return

    repo = inicializar_git(config.local_dir)
    logger.info(f"Procesando cambios del repositorio {config.local_dir}...")

    archivos = get_files(repo, config.max_file_size_bytes)
    logger.info(f"Agrupando {len(archivos)} archivos...")

    archivos_invalidos = [
        archivo[0] for archivo in archivos if archivo[2] == "invalido"
    ]
    logger.info(f"{len(archivos_invalidos)} archivos inválidos.")

    lotes = agrupar_por_lotes(archivos, config.max_batch_size_bytes)
    procesar_commits(repo, lotes, config)

    add_tag(repo, config.tag)
    add_remote(repo, config.command_remote, config.remote_name, config.local_dir)
    push_commits(repo, config.remote_name, config.branch_name)
    push_tags(repo, config.tag, config.remote_name)


def cargar_tareas() -> list[Task]:
    """Carga todas las tareas desde los archivos en la carpeta tasks."""
    tasks = []
    for file in Path("tasks").rglob("*.txt"):
        for config in Task._parsed_content(file.read_text()):
            tasks.append(Task.from_dict(config))
    return tasks


if __name__ == "__main__":
    logger.info("Iniciando gitchunk...")

    for tarea in cargar_tareas():
        procesar_tarea(tarea)

    logger.info("Finalizando gitchunk.")
