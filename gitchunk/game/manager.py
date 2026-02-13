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
        self.token = acces_token

    def process_game(self, game_path: Path):
        logger.info(f"=== Iniciando procesamiento de juego en: {game_path} ===")

        github_client = GitHubClient(token=self.token)
        scanner = GameScanner(game_path)
        cleaner = GameCleaner(game_path)
        repo_wrapper = GitchunkRepo(game_path, token=self.token)

        # ESCANEO
        metadata = scanner.scan()

        logger.info(f"ID del Juego: {metadata.save_id}")
        logger.info(f"Repositorio Objetivo: {metadata.repo_name}")
        logger.info(f"Versión Detectada: {metadata.version}")
        logger.info(f"Plataforma: {metadata.platform}")

        username = github_client.get_authenticated_user()
        if github_client.repo_exists(username, metadata.repo_name):
            remote_tags = github_client.get_remote_tags(username, metadata.repo_name)
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

        remote_url = github_client.get_or_create_repo(metadata.repo_name)
        auth_url = github_client.get_auth_url(remote_url)

        cleaner.clean()
        repo_wrapper.ensure_identity()
        repo_wrapper.configure_endpoint(remote_url, metadata.branch_name)
        repo_wrapper.synchronize()

        files_report, _, git_problems = repo_wrapper.analyze_changes()
        if files_report.invalid_files:
            logger.warning("=== ARCHIVOS OMITIDOS POR TAMAÑO ===")
            for fname, size, reason in files_report.invalid_files:
                logger.warning(f"  [X] {fname} ({size / 1024**2:.2f} MB) -> {reason}")
            logger.warning("====================================")
            return False

        if git_problems:
            logger.warning(
                f"Configuración de Git detectada: {git_problems[0]['config']}"
            )

        should_force_tag = False
        for commit in repo_wrapper.prepare_and_commit(files_report):
            if commit:
                repo_wrapper.push(delay_mins=1)
                should_force_tag = True

        tag_created = self._ensure_tag(
            repo_wrapper, metadata.tag_name, force=should_force_tag
        )
        if tag_created:
            logger.info(
                f"Etiqueta {metadata.tag_name} {'actualizada' if should_force_tag else 'creada'}."
            )
            self.push_tag_securely(
                repo_wrapper.repo, auth_url, metadata.tag_name, force=should_force_tag
            )

        logger.info(f"=== Proceso finalizado para {metadata.save_id} ===")

    def _ensure_tag(
        self, gitchunk: GitchunkRepo, tag_name: str, force: bool = False
    ) -> bool:
        """Crea o mueve el tag. Retorna True si se operó sobre el tag."""
        repo = gitchunk.repo

        if tag_name in repo.tags:
            if not force:
                logger.warning(
                    f"El tag '{tag_name}' ya existe localmente. Saltando creación."
                )
                return False

            # Si el tag ya apunta al commit actual, no hacemos nada
            if repo.tags[tag_name].commit == repo.head.commit:
                logger.info(f"El tag '{tag_name}' ya está al día con el último commit.")
                return False

            logger.info(f"Moviendo tag '{tag_name}' al nuevo commit...")
            repo.delete_tag(tag_name)  # type: ignore

        repo.create_tag(tag_name)
        return True

    def push_tag_securely(
        self, repo: Repo, auth_url: str, tag_name: str, force: bool = False
    ):
        with ephemeral_remote(repo, auth_url, "temp_tag_push") as remote:
            logger.info(f"Subiendo etiqueta {tag_name} (force={force})...")

            # El prefijo '+' en el refspec fuerza la actualización del tag en el remoto
            prefix = "+" if force else ""
            refspec = f"{prefix}refs/tags/{tag_name}:refs/tags/{tag_name}"

            infos = remote.push(refspec)
            for info in infos:
                if info.flags & (info.ERROR | info.REJECTED):
                    logger.error(f"Error al subir tag {tag_name}: {info.summary}")
                    raise Exception(f"Fallo al subir el tag: {info.summary}")
                else:
                    logger.info(f"Tag {tag_name} subido exitosamente: {info.summary}")
