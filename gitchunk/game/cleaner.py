import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class GameCleaner:
    def __init__(self, base_path: Path):
        self.path = base_path

    def clean(self):
        """
        Elimina archivos basura y compilados innecesarios.
        Protege .rpyc si no existe el .rpy correspondiente.
        """
        logger.info("Iniciando limpieza de archivos del juego...")

        self._remove_junk_folders()
        self._clean_compiled_scripts()
        self._remove_system_garbage()

    def _remove_junk_folders(self):
        """Elimina carpetas temporales y caches."""
        folders_to_nuke = ["**/cache", "**/saves", "**/tmp", "**/__pycache__"]

        for pattern in folders_to_nuke:
            for folder in self.path.glob(pattern):
                if folder.is_dir():
                    try:
                        for sub in folder.glob("**/*"):
                            if sub.is_file():
                                sub.unlink()
                            elif sub.is_dir():
                                sub.rmdir()

                        if not any(folder.iterdir()):
                            folder.rmdir()
                            logger.debug(f"Carpeta eliminada: {folder.name}")
                    except Exception as e:
                        logger.warning(f"No se pudo borrar carpeta {folder}: {e}")

    def _clean_compiled_scripts(self):
        """
        Elimina archivos compilados (.rpyc, .rpymc) SOLO si existe su fuente (.rpy, .rpym).
        """
        count_deleted = 0
        count_kept = 0

        # Lista de (patrón_compilado, extensión_fuente)
        targets = [("**/*.rpyc", ".rpy"), ("**/*.rpymc", ".rpym")]

        for pattern, source_ext in targets:
            for compiled_file in self.path.glob(pattern):
                source_file = compiled_file.with_suffix(source_ext)

                if source_file.exists():
                    try:
                        compiled_file.unlink()
                        count_deleted += 1
                    except OSError as e:
                        logger.error(f"Error borrando {compiled_file.name}: {e}")
                else:
                    count_kept += 1
                    logger.debug(
                        f"Conservado {compiled_file.name} (no se encontró código fuente {source_ext})"
                    )

        logger.info(
            f"Limpieza de scripts: {count_deleted} eliminados, {count_kept} conservados por seguridad."
        )

    def _remove_system_garbage(self):
        """Elimina basura de SO y logs."""
        patterns = [
            "**/*.pyo",
            "**/*.save",
            "**/traceback.txt",
            "**/errors.txt",
            "**/.DS_Store",
            "**/thumbs.db",
            "**/*.log",
            "**/log.txt",
            "**/traceback.txt",
        ]

        for pattern in patterns:
            for file in self.path.glob(pattern):
                if file.is_file():
                    try:
                        file.unlink()
                    except Exception:
                        pass
