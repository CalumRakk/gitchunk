import logging
from pathlib import Path

from git import Repo

from gitchunk.git_manager import ephemeral_remote
from gitchunk.github_api import GitHubClient
from gitchunk.parsing import is_version_older, parse_version

from ..core import GitchunkRepo
from .cleaner import GameCleaner
from .scanner import GameScanner

logger = logging.getLogger(__name__)


class GameManager:
    def __init__(self, acces_token: str):
        self.github = GitHubClient(token=acces_token)

    def process_game(self, game_path: Path):
        logger.info(f"=== Iniciando procesamiento de juego en: {game_path} ===")

        # ESCANEO
        scanner = GameScanner(game_path)
        metadata = scanner.scan()

        logger.info(f"ID del Juego: {metadata.save_id}")
        logger.info(f"Repositorio Objetivo: {metadata.repo_name}")
        logger.info(f"Versión Detectada: {metadata.version}")
        logger.info(f"Plataforma: {metadata.platform}")

        username = self.github.get_authenticated_user()
        if self.github.repo_exists(username, metadata.repo_name):
            remote_tags = self.github.get_remote_tags(username, metadata.repo_name)
            platform_suffix = f"-{metadata.platform}"
            versions_in_platform = [
                t.replace("v", "").replace(platform_suffix, "")
                for t in remote_tags
                if t.endswith(platform_suffix)
            ]
            if versions_in_platform:
                latest_remote = max(versions_in_platform, key=parse_version)
                if is_version_older(metadata.version, latest_remote):
                    logger.error(
                        f"FALLA DE LÓGICA: Intentando archivar {metadata.version} "
                        f"pero el remoto ya tiene la versión {latest_remote} para {metadata.platform}."
                    )
                    raise ValueError(
                        f"Regresión detectada: {metadata.version} < {latest_remote}"
                    )

        # GESTIÓN DEL REMOTO (GitHub)
        remote_url_clean = self.github.get_or_create_repo(metadata.repo_name)

        # Generamos la URL con autenticación integrada para el push
        auth_url = self.github.get_auth_url(remote_url_clean)

        # LIMPIEZA
        cleaner = GameCleaner(game_path)
        cleaner.clean()

        # OPERACIONES DE GIT
        repo_wrapper = GitchunkRepo(game_path)

        # Asegurar identidad del comitter
        author_name = "Gitchunk Bot"
        author_email = "bot@gitchunk.local"
        repo_wrapper.ensure_identity(name=author_name, email=author_email)

        repo_wrapper.set_remote(remote_url_clean)

        repo_wrapper._checkout_target_branch(metadata.branch_name)

        # Intentar optimizar (Shallow Fetch + Soft Reset)
        # Solo actúa si el repo local es nuevo
        repo_wrapper.synchronize_if_exists(
            auth_url=auth_url, branch_name=metadata.branch_name
        )

        # COMMITS
        commits_created = repo_wrapper.prepare_and_commit()

        if commits_created == 0:
            logger.info("No hay cambios nuevos para archivar.")
            # Continuamos de todos modos por si falta subir el tag o pushear

        # SUBIDA
        repo_wrapper.push_sequentially(
            auth_url=auth_url,
            branch_name=metadata.branch_name,
            delay_mins=1,
        )

        is_pc = metadata.platform.lower() in ["pc", "windows", "linux", "mac"]
        if is_pc:
            # Si es la primera subida, se establece esa plataforma como default.
            # luego cuando se detecte PC, forzamos el cambio para corregirlo
            logger.info(
                f"Plataforma PC detectada. Estableciendo {metadata.platform} como Default Branch..."
            )
            self.github.set_default_branch(metadata.repo_name, metadata.branch_name)

        logger.info(f"=== Proceso finalizado para {metadata.save_id} ===")

        # ETIQUETADO
        # Formato: v1.0.0-pc
        tag_created = self._ensure_tag(repo_wrapper, metadata.tag_name)
        if tag_created:
            logger.info(f"Etiqueta {metadata.tag_name} creada.")
            self.push_tag_securely(repo_wrapper.repo, auth_url, metadata.tag_name)

    def _ensure_tag(self, gitchunk: GitchunkRepo, tag_name: str) -> bool:
        """Crea el tag si no existe. Retorna True si se creó."""
        repo = gitchunk.repo

        if tag_name in repo.tags:
            logger.warning(
                f"El tag '{tag_name}' ya existe localmente. Saltando creación."
            )
            return False

        logger.info(f"Creando tag: {tag_name}")
        repo.create_tag(tag_name)
        return True

    def push_tag_securely(self, repo: Repo, auth_url: str, tag_name: str):
        with ephemeral_remote(repo, auth_url, "temp_tag_push") as remote:
            logger.info(f"Subiendo etiqueta {tag_name}...")

            infos = remote.push(f"refs/tags/{tag_name}:refs/tags/{tag_name}")
            for info in infos:
                if info.flags & (info.ERROR | info.REJECTED):
                    logger.error(f"Error al subir tag {tag_name}: {info.summary}")
                    raise Exception(f"Fallo al subir el tag: {info.summary}")
                else:
                    logger.info(f"Tag {tag_name} subido exitosamente: {info.summary}")
