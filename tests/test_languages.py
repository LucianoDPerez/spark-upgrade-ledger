import unittest

from src.domain import ValidationError
from src.languages import PROFILES, get_profile, t


class LanguageTests(unittest.TestCase):
    def test_all_profiles_have_the_same_keys(self):
        keys = set(PROFILES["en"].strings)
        for code, profile in PROFILES.items():
            self.assertEqual(set(profile.strings), keys, code)
            self.assertIn("source_quote", profile.system_prompt)
            self.assertIn("1 and 12 items", profile.system_prompt)

    def test_unknown_language_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "Unsupported language"):
            get_profile("fr")

    def test_translation_interpolation(self):
        profile = get_profile("zh")
        self.assertIn("3 / 5", t(profile, "approved", n=3, total=5))


if __name__ == "__main__":
    unittest.main(verbosity=2)
