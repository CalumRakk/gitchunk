import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GameMetadata:
    executable_name: str
    version: str
    platform: str
    save_id: str  # El ID único de Ren'Py (config.save_directory)

    @property
    def repo_name(self) -> str:
        """Genera el nombre estandarizado del repositorio."""
        safe_id = re.sub(r"[^a-zA-Z0-9\-_]", "-", self.save_id).lower()
        return f"gitchunk-game-{safe_id}"

    @property
    def tag_name(self) -> str:
        """Genera el tag para Git: v1.0.0-pc"""
        return f"v{self.version}-{self.platform}"

    @property
    def branch_name(self):
        return f"platform/{self.platform}"


class GameScanner:
    def __init__(self, base_path: Path | str):
        self.path = Path(base_path)

    def scan(self) -> GameMetadata:
        """Ejecuta todo el proceso de escaneo e identificación."""
        exe_name = self._find_executable()
        version = self._extract_version(self.path.name)
        platform = self._detect_platform(self.path.name)
        save_id = self._get_renpy_save_id()

        logger.info(
            f"Juego detectado: {exe_name} | Ver: {version} | Plat: {platform} | ID: {save_id}"
        )

        return GameMetadata(
            executable_name=exe_name,
            version=version,
            platform=platform,
            save_id=save_id,
        )

    def _get_renpy_config_version(self) -> Optional[str]:
        """Busca define config.version en options.rpy/rpyc."""
        game_dir = self.path / "game"
        options_rpy = game_dir / "options.rpy"
        options_rpyc = game_dir / "options.rpyc"

        pattern = re.compile(r'config\.version\s*=\s*["\']([^"\']+)["\']')
        if options_rpy.exists():
            try:
                content = options_rpy.read_text(encoding="utf-8", errors="ignore")
                match = pattern.search(content)
                if match:
                    return match.group(1)
            except Exception as e:
                logger.debug(f"Error leyendo options.rpy para versión: {e}")

        if options_rpyc.exists():
            try:
                with open(options_rpyc, "rb") as f:
                    content_bin = f.read()
                    match = pattern.search(content_bin.decode("utf-8", "ignore"))
                    if match:
                        return match.group(1)
            except Exception as e:
                logger.debug(f"Error leyendo options.rpyc para versión: {e}")

        return None

    def _find_executable(self) -> str:
        """Busca el ejecutable principal del juego."""
        blacklist = {
            "python.exe",
            "pythonw.exe",
            "zsync.exe",
            "unrpyc.exe",
            "dxwebsetup.exe",
            "python",
            "pythonw",
            "zsync",
            "uninstall.exe",
        }

        candidates = []
        for file in self.path.iterdir():
            if not file.is_file():
                continue

            if file.suffix.lower() in [".exe", ".sh", ".app"] or file.suffix == "":
                if file.name.lower() not in blacklist and not file.name.startswith("."):
                    candidates.append(file)

        if not candidates:
            raise FileNotFoundError(
                "No se encontró ningún ejecutable válido en la carpeta raíz."
            )

        # Heurística simple: el archivo más grande suele ser el ejecutable real en RenPy (a veces)
        # Por ahora devolvemos el primero o priorizamos .exe
        exe_files = [f for f in candidates if f.suffix.lower() == ".exe"]
        target = exe_files[0] if exe_files else candidates[0]

        return target.stem

    def _extract_version(self, text: str) -> str:
        """Extrae versión usando Regex en cascada."""
        # Patrón fuerte: v1.0, 1.2.3, 2023.01
        regex_strong = re.search(
            r"(?:v|ver\.?|version)\s*(\d+(?:\.\d+)+[a-z0-9\-]*)", text, re.IGNORECASE
        )
        if regex_strong:
            return regex_strong.group(1)

        # Patrón numérico simple: 0.5, 1.0 (al menos un punto)
        regex_simple = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
        if regex_simple:
            return regex_simple.group(1)

        renpy_version = self._get_renpy_config_version()
        if renpy_version:
            return renpy_version

        raise ValueError("No se pudo extraer la versión del juego.")

    def _detect_platform(self, text: str) -> str:
        """Deduce la plataforma"""
        # NOTA: otra forma de identificar es mirar dentro de `lib/`
        # parecen cosas como `py3-windows-x86_64`, `py3-linux-x86_64`
        text_lower = text.lower()

        if "-android" in text_lower or "-apk" in text_lower:
            return "android"
        if "-mac" in text_lower or "-ios" in text_lower:
            return "mac"
        if "-linux" in text_lower:
            return "linux"
        if "-pc" in text_lower or "-win" in text_lower or "-windows" in text_lower:
            # Nota: A veces "-pc" significa "todas las plataformas de escritorio"
            # Podríamos refinarlo mirando los archivos,
            # pero por ahora lo dejamos dejamos que el análisis de archivos lo confirme.
            pass

        return self._analyze_files_for_platform()

    def _analyze_files_for_platform(self) -> str:
        """
        Escanea la carpeta raíz para determinar la plataforma según los ejecutables.
        """
        has_exe = False
        has_sh = False
        has_app = False
        has_apk = False

        for item in self.path.iterdir():
            name_lower = item.name.lower()

            if name_lower.startswith("."):
                continue

            if item.is_file():
                if item.suffix.lower() == ".exe" and name_lower not in [
                    "unins000.exe",
                    "uninstall.exe",
                ]:
                    has_exe = True
                elif item.suffix.lower() == ".sh":
                    has_sh = True
                elif item.suffix.lower() == ".apk":
                    has_apk = True

            elif item.is_dir():
                # En Mac, las aplicaciones son carpetas terminadas en .app
                if item.suffix.lower() == ".app":
                    has_app = True

        if has_apk:
            return "android"

        # Si tiene los tres (o Win+Linux, o Win+Mac), suele ser la build "Market" o "PC" universal
        if has_exe and (has_sh or has_app):
            return "pc"

        if has_exe:
            return "windows"

        if has_app:
            return "mac"

        if has_sh:
            return "linux"

        raise ValueError("No se pudo determinar la plataforma del juego.")

    def _get_renpy_save_id(self) -> str:
        """
        Busca config.save_directory en options.rpy/rpyc.
        """
        game_dir = self.path / "game"
        options_rpy = game_dir / "options.rpy"
        options_rpyc = game_dir / "options.rpyc"

        # Regex para buscar: config.save_directory = "MyGame-123"
        pattern = re.compile(r'config\.save_directory\s*=\s*["\']([^"\']+)["\']')

        # Intentar leer el código fuente
        if options_rpy.exists():
            try:
                content = options_rpy.read_text(encoding="utf-8", errors="ignore")
                match = pattern.search(content)
                if match:
                    return match.group(1)
            except Exception:
                pass

        # Intentar leer binario compilado
        if options_rpyc.exists():
            try:
                with open(options_rpyc, "rb") as f:
                    content_bin = f.read()
                    match = pattern.search(content_bin.decode("utf-8", "ignore"))
                    if match:
                        return match.group(1)
            except Exception:
                pass

        raise ValueError("No se pudo encontrar el ID de guardado.")
