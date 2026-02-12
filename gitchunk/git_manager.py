import configparser
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Generator, Optional, cast, get_args

import git
from git import Actor, GitCommandError, List, Remote, Repo
from git.types import Lit_config_levels

from .schemas import (
    Batchs,
    CheckUserEmail,
    FileRename,
    GitStatus,
    StatusStaged,
    StatusUnstaged,
    SyncStatus,
)

logger = logging.getLogger(__name__)


@contextmanager
def ephemeral_remote(
    repo: Repo, auth_url: str, remote_name: str = "temp_auth_remote"
) -> Generator[Remote, None, None]:
    """
    Context Manager que crea un remoto temporal seguro y garantiza su eliminación.
    Uso:
        with ephemeral_remote(repo, url_con_token) as remote:
            remote.push(...)
    """
    remote = Remote(repo, remote_name)
    if remote in repo.remotes:
        logger.warning(
            f"Remoto temporal {remote_name} encontrado y eliminado antes de usar."
        )
        repo.delete_remote(remote)

    remote = repo.create_remote(remote_name, auth_url)
    try:
        yield remote
    finally:
        if remote_name in repo.remotes:
            repo.delete_remote(remote)


def get_sync_status(repo: Repo, remote: Remote, branch_name: str) -> SyncStatus:
    """
    Determina la relación topológica entre el HEAD local y la rama remota.
    No modifica el repositorio.
    """
    try:
        remote_refs = repo.git.ls_remote(remote.name, branch_name)
    except GitCommandError:
        return SyncStatus.NO_REMOTE

    if not remote_refs:
        return SyncStatus.NO_REMOTE

    remote.fetch(branch_name, depth=1)
    remote_ref = f"{remote.name}/{branch_name}"

    if is_repo_new(repo):
        return SyncStatus.BEHIND  # Si local está vacío, técnicamente estamos "atrás".

    local_commit = repo.head.commit
    remote_commit = repo.commit(remote_ref)

    if local_commit == remote_commit:
        return SyncStatus.EQUAL

    # Análisis de Ancestros
    # ¿Es el remoto un ancestro del local? -> Entonces vamos ganando (AHEAD)
    try:
        if repo.is_ancestor(remote_commit, local_commit):
            return SyncStatus.AHEAD
    except GitCommandError:
        pass

    # ¿Es el local un ancestro del remoto? -> Entonces vamos perdiendo (BEHIND)
    try:
        if repo.is_ancestor(local_commit, remote_commit):
            return SyncStatus.BEHIND
    except GitCommandError:
        pass

    # Si no es ninguno de los anteriores, han divergido
    return SyncStatus.DIVERGED


def sync_with_remote_shallow(repo: Repo, auth_url: str, branch_name: str) -> bool:
    """
    Sincroniza el repositorio local actuando según el estado detectado.
    """
    logger.info("Verificando estado de sincronización con el remoto...")

    with ephemeral_remote(repo, auth_url, "temp_sync") as remote:
        status = get_sync_status(repo, remote, branch_name)
        remote_ref = f"{remote.name}/{branch_name}"

        match status:
            case SyncStatus.NO_REMOTE:
                logger.info(
                    f"Rama remota '{branch_name}' no existe. Se iniciará historial nuevo."
                )
                return False

            case SyncStatus.EQUAL:
                logger.info("El repositorio ya está sincronizado.")
                return True

            case SyncStatus.AHEAD:
                logger.info(
                    "ESTADO: AHEAD (Resume). "
                    "Se detectaron commits locales pendientes de subir. "
                    "NO se realizará reset para preservar el trabajo."
                )
                return True

            case SyncStatus.BEHIND:
                logger.info(
                    "ESTADO: BEHIND (Update). Actualizando base local al último commit remoto..."
                )
                repo.git.reset(remote_ref)
                return True

            case SyncStatus.DIVERGED:
                logger.warning(
                    "ESTADO: DIVERGED. Las historias han divergido. "
                    "Se forzará la alineación al remoto (reset --soft) manteniendo archivos."
                )
                repo.git.reset("--soft", remote_ref)
                return True

        return False


def fix_dubious_ownership(path: Path) -> bool:
    """
    Intenta marcar el directorio como seguro para Git de forma global.
    """
    import subprocess

    try:
        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "--add",
                "safe.directory",
                str(path.absolute()),
            ],
            check=True,
        )
        logger.info(f"Directorio {path} marcado como seguro exitosamente.")
        return True
    except Exception as e:
        logger.error(f"No se pudo marcar el directorio como seguro: {e}")
        return False


def get_git_status(repo: Repo):
    """
    Obtiene el estado actual del repositorio Git.

    El estado se devuelve como un diccionario con dos claves: "staged" y "unstaged".
    "staged" contiene los archivos que han sido modificados o eliminados y
    están en el stage, mientras que "unstaged" contiene los archivos que han sido
    modificados o eliminados pero no están en el stage.

    Los archivos en "staged" se clasifican en tres categorías:
    - "added": Archivos nuevos que han sido añadidos al stage.
    - "modified": Archivos existentes que han sido modificados y
      añadidos al stage.
    - "deleted": Archivos existentes que han sido eliminados y
      añadidos al stage.
    - "renamed": Archivos existentes que han sido renombrados y
      añadidos al stage.

    Los archivos en "unstaged" se clasifican en tres categorías:
    - "modified": Archivos existentes que han sido modificados pero
      no se han agregado al stage.
    - "deleted": Archivos existentes que han sido eliminados pero
      no se han agregado al stage.
    - "untracked": Archivos que no están en el index ni en algún commit,
      respetando .gitignore.
    """
    if repo.head.is_valid():
        repo.index.reset()

    unstaged = StatusUnstaged(modified=[], deleted=[], untracked=repo.untracked_files)
    staged = StatusStaged(added=[], modified=[], deleted=[], renamed=[])

    # repo.index.diff(None) Devuelve los archivos modificados o eliminados que aún no has pasado al stage.
    # repo.index.diff(None) No devuelve los archivos untracked, porque aún no existe en el index (se obtienen con repo.untracked_files)
    # repo.untracked_files Devuelve la lista archivos que no están en el index ni en ningún commit, respetando .gitignore
    for diff in repo.index.diff(None):
        a_path = cast(str, diff.a_path)
        if (
            diff.change_type == "M"
        ):  # Archivo existente modificado, no se ha agregado a stage.
            unstaged["modified"].append(a_path)
        elif (
            diff.change_type == "D"
        ):  # Archivo existente eliminado, no se ha agregado a stage.
            unstaged["deleted"].append(a_path)
        else:
            logger.error(f"Unknown change type: {diff.change_type}")

    if not is_repo_new(repo):
        for diff in repo.index.diff("HEAD"):
            a_path = cast(str, diff.a_path)
            if diff.change_type == "A":  # Archivo nuevo añadido a stage.
                staged["added"].append(a_path)
            elif (
                diff.change_type == "M"
            ):  # Archivo existente modificado y añadido a stage.
                staged["modified"].append(a_path)
            elif (
                diff.change_type == "D"
            ):  # Archivo existente eliminado y añadido a stage.
                staged["deleted"].append(a_path)
            elif (
                diff.change_type == "R"
            ):  # Archivo existente renombrado y añadido a stage.
                rename_from = cast(str, diff.rename_from)
                rename_to = cast(str, diff.rename_to)
                staged["renamed"].append(
                    FileRename(old_name=rename_from, new_name=rename_to)
                )
            else:
                logger.error(f"Unknown change type: {diff.change_type}")
    else:
        for path, _stage in repo.index.entries.keys():
            path = cast(str, path)
            staged["added"].append(path)

    return GitStatus(staged=staged, unstaged=unstaged)


def push_commits_one_by_one(repo, auth_url, branch_name, delay_minutes=5):
    with ephemeral_remote(repo, auth_url, "temp_sync") as sync_remote:
        sync_remote.fetch()

        remote_ref = f"{sync_remote.name}/{branch_name}"

        try:
            repo.git.rev_parse("--verify", remote_ref)
            rev_range = f"{remote_ref}..{branch_name}"
        except GitCommandError:
            # Si no existe (repositorio nuevo o rama nueva),
            # tomamos todos los commits de la rama local
            logger.info(
                f"La rama remota {remote_ref} no existe. Se subirán todos los commits."
            )
            rev_range = branch_name

        commits = list(repo.iter_commits(rev_range))

        for index, commit in enumerate(reversed(commits), start=1):
            sync_remote.push(
                refspec=f"{commit.hexsha}:refs/heads/{branch_name}",
                force_with_lease=True,
            )
            logger.info(f"Push commit {commit.hexsha} exitoso")
            if index < len(commits):
                logger.info(f"Esperando {delay_minutes} minutos...")
                sleep(delay_minutes * 60)


def batch_list(items, batch_size):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


def remove_files_from_index(repo: Repo, files: List[str]) -> None:
    for batch in batch_list(files, 100):
        try:
            repo.index.remove(batch, working_tree=True)
        except GitCommandError as e:
            try:
                for i in batch:
                    repo.index.remove(i, working_tree=True)
            except GitCommandError as e:
                logger.error(f"Error al eliminar archivos: {e}")


def create_commits(
    repo: Repo, batchs: Batchs, author: Actor
) -> Generator[git.Commit, None, None]:
    total_steps = len(batchs["to_add"]) + (1 if batchs["to_delete"] else 0)
    current_step = 1

    def get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if batchs["to_delete"]:
        num_deleted = len(batchs["to_delete"])
        logger.info(
            f"[{current_step}/{total_steps}] Eliminando {num_deleted} archivos del índice..."
        )

        remove_files_from_index(repo, batchs["to_delete"])

        msg = f"Batch {current_step}/{total_steps} | Delete {num_deleted} files | {get_timestamp()}"
        commit = repo.index.commit(msg, author=author, committer=author)
        yield commit
        current_step += 1

    for files in batchs["to_add"]:
        num_files = len(files)

        sample_files = (
            f"{files[0]}... (+{num_files-1} más)" if num_files > 1 else files[0]
        )
        logger.info(
            f"[{current_step}/{total_steps}] Añadiendo {num_files} archivos: {sample_files}"
        )

        repo.index.add(files)

        msg = f"Batch {current_step}/{total_steps} | Add {num_files} files | {get_timestamp()}"
        commit = repo.index.commit(msg, author=author, committer=author)

        yield commit

        logger.debug(f"Commit {commit.hexsha[:7]} creado exitosamente.")
        current_step += 1

    logger.info(f"Proceso de commits finalizado.")


def is_repo_new(repo: Repo):
    """Devuelve True si el repositorio es nuevo. Un repositorio es nuevo si no tiene commits."""
    # try:
    #     # Intenta acceder al commit HEAD
    #     _ = repo.head.commit
    #     return False
    # except (ValueError, exc.BadName, exc.GitCommandError):
    #     # ValueError → HEAD no existe (repo vacío)
    #     # BadName → referencia no válida
    #     # GitCommandError → fallo al ejecutar comando git
    #     return True
    return not repo.head.is_valid()


def set_local_user_email(
    repo: Repo, name, email, level: Lit_config_levels = "repository"
) -> CheckUserEmail:
    with repo.config_writer(config_level=level) as config:
        config.set_value("user", "name", name)
        config.set_value("user", "email", email)

    return check_git_user_email(repo, level)


def get_explicit_user_email(repo: Repo):
    explicit = {}

    for level in get_args(Lit_config_levels):
        try:
            config = repo.config_reader(config_level=level)
            name = config.get_value("user", "name")
            email = config.get_value("user", "email")
            explicit[level] = {"user.name": name, "user.email": email}
        except (KeyError, configparser.NoOptionError, configparser.NoSectionError):
            continue

    return explicit


def set_safe_repo(repo: git.Repo) -> None:
    repo.git.config("--global", "--add", "safe.directory", str(repo.working_tree_dir))


def is_safe_repo(repo: git.Repo) -> bool:
    try:
        repo.git.status()
        print("Repositorio seguro ")
        return True
    except GitCommandError as e:
        if "dubious ownership" in str(e):
            return False

    raise Exception("Error desconocido al verificar el repositorio.")


def get_remote(repo: Repo, remote_name: str = "origin") -> Optional[Remote]:
    for remote in repo.remotes:
        if remote.name == remote_name:
            return remote
    return None


def check_git_user_email(repo: Repo, level: Lit_config_levels) -> CheckUserEmail:
    config = repo.config_reader(config_level=level)

    user_name = None
    user_email = None

    # Intenta obtener user.name y user.email
    try:
        user_name = cast(str, config.get_value("user", "name"))
    except (KeyError, configparser.NoOptionError, configparser.NoSectionError):
        pass

    try:
        user_email = cast(str, config.get_value("user", "email"))
    except (KeyError, configparser.NoOptionError, configparser.NoSectionError):
        pass

    return CheckUserEmail(
        user_name=user_name,
        user_email=user_email,
        is_configured=user_name is not None and user_email is not None,
    )


def init_repo(folder: Path | str) -> Repo:
    folder = Path(folder) if isinstance(folder, str) else folder
    if isinstance(folder, str):
        folder = Path(folder)

    if not (folder / ".git").exists():
        repo = Repo.init(folder)
        return repo
    else:
        return Repo((folder / ".git"))


def get_problematic_git_configs(repo: Repo) -> list[dict]:
    """
    Detecta configuraciones de Git (globales o de sistema) que podrían
    hacer que archivos importantes sean ignorados.
    """
    problems = []

    try:
        global_ignore = repo.git.config("--get", "core.excludesfile")
        if global_ignore and Path(global_ignore).exists():
            problems.append(
                {
                    "config": "core.excludesfile",
                    "value": global_ignore,
                    "reason": "Tienes un archivo de ignore global que podría estar ocultando ejecutables (.exe, .dll) o carpetas del juego.",
                }
            )
    except GitCommandError:
        # Si no existe la config, git devuelve error 1, es normal.
        pass

    return problems
