import unittest
from gitchunk.utils import get_game_name, get_game_version


class TestGameNameExtraction(unittest.TestCase):
    def setUp(self):
        self.test_cases = [
            ("Game_Rabbit2_Release-0.3-", "Game_Rabbit2", "0.3"),
            ("game-StarPy-pc", "game-StarPy", None),
            ("game-Red-Mansion-2-pc", "game-Red-Mansion-2", None),
            ("Vice-0.9-pc", "Vice", "0.9"),
            ("Vice_15-0.9-apk", "Vice_15", "0.9"),
            ("Witches2 magic-0.2-mac", "Witches2 magic", "0.2"),
            ("Witches 4 magic-release-mac", "Witches 4 magic", None),
            ("Lord Rings 2-0.4.1-apk", "Lord Rings 2", "0.4.1"),
            ("Super_Game_1.2.3", "Super_Game", "1.2.3"),
            ("Another_Game_Release-2.0", "Another_Game", "2.0"),
            ("Just_A_Game", None, None),
            (
                "No_Version_Here",
                "No",
                None,
            ),  # Coincide el name por contener la palabra "Version"
            ("Game_With_Multiple_Dashes-1.0-pc", "Game_With_Multiple_Dashes", "1.0"),
            ("Game_With_No_Version", "Game_With_No", None),
            ("Game With_Only_Release_Release-", "Game With_Only", None),
            ("Game_With_Only_Version-1.0", "Game_With_Only", "1.0"),
            ("Game_With_Only_v2.0.1", "Game_With_Only", "2.0.1"),
            ("Normal_game_v2.2.5_EN_for", "Normal_game", "2.2.5"),
            ("The Game v5 v1.00.5 Preview Build Part 9", "The Game", "1.00.5"),
        ]

    def test_game_names(self):
        for filename, name, version in self.test_cases:
            with self.subTest(filename=filename):
                result = get_game_name(filename)
                self.assertEqual(result, name)

    def test_game_versions(self):
        for filename, name, version in self.test_cases:
            with self.subTest(filename=filename):
                result = get_game_version(filename)
                self.assertEqual(result, version)


if __name__ == "__main__":
    unittest.main()
