import logging
from pathlib import Path
from typing import Optional

from git import Actor, Repo, exc

from gitchunk.schemas import Batchs, FilesFiltered

from .git_manager import (
    check_git_user_email,
    create_commits,
    fix_dubious_ownership,
    get_git_status,
    get_problematic_git_configs,
    get_remote,
    is_repo_new,
    push_commits_one_by_one,
    set_local_user_email,
    sync_with_remote_shallow,
)
from .processing import batch_files, filter_files_from_status

logger = logging.getLogger(__name__)


class GitchunkRepo:
    def __init__(self, path: Path, token: Optional[str] = None):
        self.path = path
        self.repo = self._open_or_init()
        self.author: Optional[Actor] = None
        self.token = token
        self._remote_url: Optional[str] = None
        self._branch_name: str = "master"

    @property
    def auth_url(self) -> Optional[str]:
        if not self._remote_url or not self.token:
            return self._remote_url
        return self._remote_url.replace("https://", f"https://{self.token}@")

    def configure_endpoint(self, remote_url: str, branch_name: str):
        """Configura el destino una sola vez."""
        self._remote_url = remote_url
        self._branch_name = branch_name
        self._set_remote(remote_url)
        self._checkout_target_branch(branch_name)

    def synchronize(self):
        if self.auth_url:
            return sync_with_remote_shallow(self.repo, self.auth_url, self._branch_name)

    def push(self, delay_mins: int = 5):
        return push_commits_one_by_one(
            repo=self.repo,
            auth_url=self.auth_url,
            branch_name=self._branch_name,
            delay_minutes=delay_mins,
        )

    def analyze_changes(self) -> tuple[FilesFiltered, Batchs, list[dict]]:
        """
        Analiza el estado actual y prepara los lotes de cambios.
        No realiza ninguna modificación en el repositorio.
        """
        logger.info("Analizando archivos para backup...")
        git_problems = get_problematic_git_configs(self.repo)

        status = get_git_status(self.repo)

        files_filtered = filter_files_from_status(self.path, status)
        batches = batch_files(files_filtered)

        return files_filtered, batches, git_problems

    def commit_changes(self, batches: Batchs) -> int:
        """
        Ejecuta los commits basados en los lotes calculados previamente.
        """
        if not self.author:
            raise ValueError("Debes llamar a ensure_identity() antes de hacer commits.")

        if not batches["to_add"] and not batches["to_delete"]:
            logger.info("No hay cambios válidos para confirmar.")
            return 0

        logger.info("Aplicando cambios al repositorio...")
        commits = create_commits(self.repo, batches, self.author)

        logger.info(f"Se han generado {len(commits)} commits nuevos.")
        return len(commits)

    def ensure_identity(
        self, name: str = "Gitchunk Bot", email: str = "bot@gitchunk.local"
    ):
        """Asegura que el repo tenga un usuario configurado para firmar commits."""
        status = check_git_user_email(self.repo, "repository")
        if not status["is_configured"]:
            logger.info(f"Configurando identidad local: {name} <{email}>")
            set_local_user_email(self.repo, name, email)

        self.author = Actor(name, email)

    def _open_or_init(self) -> Repo:
        """Abre o inicializa el repo y verifica inmediatamente la propiedad."""
        if not (self.path / ".git").exists():
            logger.info(f"Inicializando nuevo repositorio Git en {self.path}")
            repo = Repo.init(self.path)
        else:
            repo = Repo(self.path)

        try:
            # 'rev-parse --is-inside-work-tree' es un comando muy ligero
            # que obliga a Git a validar el repositorio.
            repo.git.rev_parse("--is-inside-work-tree")
        except exc.GitCommandError as e:
            if "dubious ownership" in str(e).lower():
                logger.warning(
                    f"Propiedad dudosa detectada en {self.path}. Intentando auto-reparación..."
                )
                if fix_dubious_ownership(self.path):
                    return repo
                else:
                    raise Exception(
                        "No se pudo resolver el problema de propiedad de Git."
                    )
            raise e

        return repo

    def _set_remote(self, remote_url: str, remote_name: str = "origin"):
        """Configura o actualiza la URL del remoto."""
        remote = get_remote(self.repo, remote_name)
        if not remote:
            logger.info(f"Añadiendo remoto {remote_name}: {remote_url}")
            self.repo.create_remote(remote_name, remote_url)
        else:
            logger.info(f"Actualizando URL del remoto {remote_name}")
            remote.set_url(remote_url)

    def _checkout_target_branch(self, branch_name: str):
        """
        Asegura que el repositorio esté en la rama de la plataforma correcta.
        """
        if is_repo_new(self.repo):
            # Si el repo es nuevo, cambiamos el nombre de la rama actual (HEAD)
            # de forma "silenciosa" sin activar las protecciones de checkout.
            logger.info(f"Configurando rama inicial como: {branch_name}")
            self.repo.git.symbolic_ref("HEAD", f"refs/heads/{branch_name}")
        else:
            # Si el repo ya tiene commits, usamos el checkout normal.
            try:
                current_branch = self.repo.active_branch.name
                if current_branch != branch_name:
                    logger.info(f"Cambiando a rama de plataforma: {branch_name}")
                    # Usamos -B para forzar o crear si es necesario
                    self.repo.git.checkout("-B", branch_name)
            except TypeError:
                # Caso borde: HEAD no apunta a una rama (detached)
                self.repo.git.checkout("-B", branch_name)
