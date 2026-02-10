import unittest
from pathlib import Path
from unittest.mock import patch

from gitchunk.game.manager import GameManager
from gitchunk.game.scanner import GameMetadata


class TestArchivingFlowRules(unittest.TestCase):

    def setUp(self):
        """Configuración base para todos los tests."""
        self.dummy_path = Path("/dummy/game/path")
        self.manager = GameManager(acces_token="fake_token")

    @patch("gitchunk.game.manager.GitHubClient")
    @patch("gitchunk.game.manager.GameScanner")
    @patch("gitchunk.game.manager.GameCleaner")
    @patch("gitchunk.game.manager.GitchunkRepo")
    def test_rule_1_branches_per_platform(
        self, MockRepo, MockCleaner, MockScanner, MockGitHub
    ):
        """
        # Segregar plataformas.
        Verifica que el sistema seleccione la rama correcta basada EXCLUSIVAMENTE
        en la plataforma detectada.
        """
        scanner_instance = MockScanner.return_value
        repo_instance = MockRepo.return_value
        repo_instance.analyze_changes.return_value = (
            {"invalid_files": []},
            {"to_add": [], "to_delete": []},
        )

        # Detectamos Windows
        scanner_instance.scan.return_value = GameMetadata(
            executable_name="game.exe",
            version="1.0",
            platform="windows",
            save_id="my_game",
        )

        self.manager.process_game(self.dummy_path)

        # Verificamos
        args, _ = repo_instance.configure_endpoint.call_args
        branch_used = args[1]
        self.assertEqual(
            branch_used,
            "platform/windows",
            "Error: La plataforma Windows debe ir a la rama 'platform/windows'",
        )

        # Detectamos Android
        scanner_instance.scan.return_value = GameMetadata(
            executable_name="game.apk",
            version="1.0",
            platform="android",
            save_id="my_game",
        )

        self.manager.process_game(self.dummy_path)

        args, _ = repo_instance.configure_endpoint.call_args
        branch_used = args[1]
        self.assertEqual(
            branch_used,
            "platform/android",
            "Error: La plataforma Android debe ir a la rama 'platform/android'",
        )

    @patch("gitchunk.game.manager.GitHubClient")
    @patch("gitchunk.game.manager.GameScanner")
    @patch("gitchunk.game.manager.GameCleaner")
    @patch("gitchunk.game.manager.GitchunkRepo")
    def test_rule_2_strict_linearity(
        self, MockRepo, MockCleaner, MockScanner, MockGitHub
    ):
        """
        # Linealidad y Anti-Regresión.
        Si intento subir v1.0 sobre una rama que ya tiene v2.0, debe fallar.
        """
        gh_instance = MockGitHub.return_value
        scanner_instance = MockScanner.return_value

        # Escenario: El remoto ya existe
        gh_instance.repo_exists.return_value = True
        # El remoto tiene la versión 2.0 para PC
        gh_instance.get_remote_tags.return_value = ["v2.0.0-pc"]

        # Escenario Local: Tenemos una versión VIEJA (1.0)
        scanner_instance.scan.return_value = GameMetadata(
            executable_name="game.exe",
            version="1.0.0",
            platform="pc",
            save_id="my_game",
        )

        with self.assertRaises(ValueError) as context:
            self.manager.process_game(self.dummy_path)

        self.assertIn("Regresión detectada", str(context.exception))

        # Asegurar que NO se hizo push ni commit
        MockRepo.return_value.commit_changes.assert_not_called()
        MockRepo.return_value.push.assert_not_called()

    @patch("gitchunk.game.manager.GitHubClient")
    @patch("gitchunk.game.manager.GameScanner")
    @patch("gitchunk.game.manager.GameCleaner")
    @patch("gitchunk.game.manager.GitchunkRepo")
    def test_rule_2b_linear_independence_between_platforms(
        self, MockRepo, MockCleaner, MockScanner, MockGitHub
    ):
        """
        REGLA 2 (Excepción): Independencia.
        Si existe v2.0 en LINUX, eso NO debe impedir subir v1.0 en WINDOWS.
        """
        gh_instance = MockGitHub.return_value
        scanner_instance = MockScanner.return_value
        repo_instance = MockRepo.return_value

        repo_instance.analyze_changes.return_value = (
            {"invalid_files": []},
            {"to_add": [], "to_delete": []},
        )

        gh_instance.repo_exists.return_value = True

        # El remoto tiene v2.0 pero es de LINUX
        gh_instance.get_remote_tags.return_value = ["v2.0.0-linux"]

        # Localmente tenemos v1.0 pero es de WINDOWS
        scanner_instance.scan.return_value = GameMetadata(
            executable_name="game.exe",
            version="1.0.0",
            platform="windows",
            save_id="my_game",
        )

        self.manager.process_game(self.dummy_path)

        # Verificar que efectivamente se configuró el repo (el proceso avanzó)
        repo_instance.configure_endpoint.assert_called()


if __name__ == "__main__":
    unittest.main()
