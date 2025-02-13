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


def procesar_tarea(config: Task):
    logger.info("".join(["-" for i in range(75)]))
    if not config.local_dir.exists():
        logger.error(f"La carpeta de trabajo no existe: {config.local_dir}")
        return

    # mutar
    if config.command_remote is not None and config.command_remote.lower() == "auto":
        logger.info("Buscando tarea automática...")
        task_folder = Path("tasks") / "auto"
        game_name = get_game_name(config.local_dir.parent.name) or get_game_name(
            config.local_dir.name
        )
        game_version = get_game_version(
            config.local_dir.parent.name
        ) or get_game_version(config.local_dir.name)
        task_path = task_folder / f"{game_name}.txt"
        if task_path.exists():
            logger.info(f"Usando tarea automática: {task_path}")
            config = Task.from_filepath(task_path)
            config.tag = game_version
        else:
            logger.info(f"Creando tarea automática: {task_path}")
            response = creata_repostirotio(repo_name=game_name, private=True)
            # build git_url
            repo_full_name = response["full_name"]
            command_remote = (
                f"git remote add origin git@{config.host_github}:{repo_full_name}.git"
            )
            config_text = f"local_dir={config.local_dir}\nauthor_name={config.author_name}\nauthor_email={config.author_email}\ncommand_remote={command_remote}\ntag={game_version}"
            task_path.parent.mkdir(parents=True, exist_ok=True)
            task_path.write_text(config_text)

    repo = inicializar_git(config.local_dir)
    logger.info(f"Procesando cambios del repositorio {config.local_dir}...")
    files = get_files(repo, config.max_file_size_bytes)
    logger.info(f"Agrupando {len(files)} archivos...")

    files_invalidos = [file[0] for file in files if file[2] == "invalido"]
    logger.info(f"{len(files_invalidos)} archivos inválidos.")
    lotes = agrupar_por_lotes(files, config.max_batch_size_bytes)
    logger.info(f"Creando {len(lotes)} commits.")

    for lote_index, lote in enumerate(lotes, start=1):
        logger.info(f"Creando commit {lote_index}/{len(lotes)}...")
        if len(lote) > 200:
            logger.info(f"Más de 200 archivos en el lote, esto puede tardar...")

        add_files(lote, repo)
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        message = f"{date} - Lote ({lote_index}/{len(lotes)}) ({len(lote)} archivos)"
        repo.index.commit(message, author=config.author, committer=config.committer)
        logger.info(f"Commit creado exitosamente.")
    add_tag(repo, config.tag)
    add_remote(repo, config.command_remote, config.remote_name, config.local_dir)
    push_commits(repo, config.remote_name, config.branch_name)
    push_tags(repo, config.tag, config.remote_name)


if __name__ == "__main__":
    logger.info("Iniciando gitchunk...")
    tasks = [
        Task.from_dict(config)
        for file in Path("tasks").rglob("*.txt")
        for config in Task._parsed_content(file.read_text())
    ]
    for config in tasks:
        procesar_tarea(config)
    logger.info("Finalizando gitchunk.")
