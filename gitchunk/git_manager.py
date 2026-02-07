import configparser
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Generator, Optional, cast, get_args

import git
from git import Actor, Commit, GitCommandError, List, Remote, Repo
from git.types import Lit_config_levels

from .schemas import (
    Batchs,
    CheckUserEmail,
    FileRename,
    GitStatus,
    StatusStaged,
    StatusUnstaged,
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


def sync_with_remote_shallow(repo: Repo, auth_url: str, branch_name: str):
    """
    Realiza un fetch de profundidad 1 usando una URL con token
    y mueve el HEAD al commit del remoto (soft reset).
    """
    with ephemeral_remote(repo, auth_url, "temp_sync") as remote:
        remote.fetch(branch_name, depth=1)  # TODO: LLEVA TIEMPO
        remote_ref = f"{remote.name}/{branch_name}"
        repo.git.reset(remote_ref)  # TODO: LLEVA TIEMPO
        return True


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


def create_commits(repo: Repo, batchs: Batchs, author: Actor) -> List[Commit]:
    commits = []
    total_steps = len(batchs["to_add"]) + (1 if batchs["to_delete"] else 0)
    current_step = 1

    def get_timestamp():
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if batchs["to_delete"]:
        num_deleted = len(batchs["to_delete"])
        logger.info(
            f"[{current_step}/{total_steps}] Eliminando {num_deleted} archivos del índice..."
        )

        repo.index.remove(batchs["to_delete"], working_tree=True)

        msg = f"Batch {current_step}/{total_steps} | Delete {num_deleted} files | {get_timestamp()}"
        commit = repo.index.commit(msg, author=author, committer=author)
        commits.append(commit)
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

        commits.append(commit)

        logger.debug(f"Commit {commit.hexsha[:7]} creado exitosamente.")
        current_step += 1

    logger.info(f"Proceso de commits finalizado. {len(commits)} commits generados.")
    return commits


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
