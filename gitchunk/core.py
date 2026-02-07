import logging
from pathlib import Path
from typing import Optional

from git import Actor, Repo, exc

from .git_manager import (
    check_git_user_email,
    create_commits,
    fix_dubious_ownership,
    get_git_status,
    get_remote,
    is_repo_new,
    push_commits_one_by_one,
    set_local_user_email,
    sync_with_remote_shallow,
)
from .processing import batch_files, filter_files_from_status

logger = logging.getLogger(__name__)


class GitchunkRepo:
    def __init__(self, path: Path):
        self.path = path
        self.repo = self._open_or_init()
        self.author: Optional[Actor] = None

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

    def ensure_identity(
        self, name: str = "Gitchunk Bot", email: str = "bot@gitchunk.local"
    ):
        """Asegura que el repo tenga un usuario configurado para firmar commits."""
        status = check_git_user_email(self.repo, "repository")
        if not status["is_configured"]:
            logger.info(f"Configurando identidad local: {name} <{email}>")
            set_local_user_email(self.repo, name, email)

        self.author = Actor(name, email)

    def set_remote(self, remote_url: str, remote_name: str = "origin"):
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

    def prepare_and_commit(self) -> int:
        """
        Analiza archivos, crea lotes y genera los commits.
        Devuelve el número de commits creados.
        """
        if not self.author:
            raise ValueError("Debes llamar a ensure_identity() antes de hacer commits.")

        logger.info("Analizando archivos y preparando lotes...")
        status = get_git_status(self.repo)
        files = filter_files_from_status(self.path, status)
        batches = batch_files(files)

        commits = create_commits(self.repo, batches, self.author)

        logger.info(f"Se han generado {len(commits)} commits nuevos.")
        return len(commits)

    def push_sequentially(
        self,
        auth_url: Optional[str] = None,
        remote_name: str = "origin",
        branch_name: str = "master",
        delay_mins: int = 5,
    ):
        """
        Sube los commits uno por uno.

        Args:
            auth_url: URL que incluye el token (https://token@github.com/...).
                      Si se provee, se usará esta URL para el transporte,
                      pero 'remote_name' se usará para calcular referencias.
        """
        push_target = auth_url if auth_url else remote_name

        logger.info(f"Iniciando subida secuencial a {remote_name}/{branch_name}...")
        push_commits_one_by_one(
            repo=self.repo,
            auth_url=auth_url,
            branch_name=branch_name,
            delay_minutes=delay_mins,
        )

    def synchronize_if_exists(self, auth_url: str, branch_name: str):
        """
        Sincroniza metadatos usando la URL autenticada.
        """
        if is_repo_new(self.repo):
            # Ahora pasamos la auth_url que contiene el token
            success = sync_with_remote_shallow(self.repo, auth_url, branch_name)

            if success:
                logger.info("Sincronización inicial exitosa.")
            else:
                logger.info(f"No se encontró historial previo para '{branch_name}'.")
