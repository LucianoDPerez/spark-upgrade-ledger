import unittest

from src.domain import ValidationError
from src.validator import parse_draft, validate_draft

SOURCE = (
    "cortiq 0.8.67 adds a native CUDA backend, and Spark-X2.6-4B is the first model it runs.\n"
    "Past 8192 tokens the Turbo far field takes over, on CUDA as well."
)


def payload(**overrides):
    item = {
        "id": "C1",
        "title": "cortiq 0.8.67 agrega backend CUDA nativo",
        "affects": "motor CUDA",
        "source_quote": "cortiq 0.8.67 adds a native CUDA backend",
        "breaking": False,
    }
    item.update(overrides)
    return {"items": [item]}


class ParseDraftTests(unittest.TestCase):
    def test_parses_plain_json(self):
        import json

        self.assertEqual(parse_draft(json.dumps(payload())), payload())

    def test_parses_fenced_json(self):
        import json

        raw = "```json\n" + json.dumps(payload()) + "\n```"
        self.assertEqual(parse_draft(raw), payload())

    def test_rejects_non_json(self):
        with self.assertRaisesRegex(ValidationError, "not valid JSON"):
            parse_draft("here is your checklist")

    def test_rejects_extra_top_level_keys(self):
        import json

        bad = {**payload(), "note": "extra"}
        with self.assertRaisesRegex(ValidationError, "schema mismatch"):
            parse_draft(json.dumps(bad))


class ValidateDraftTests(unittest.TestCase):
    def test_accepts_grounded_item(self):
        outcome = validate_draft(payload(), SOURCE)
        items = outcome.items
        self.assertEqual(items[0].id, "C1")
        self.assertFalse(items[0].breaking)

    def test_rejects_invented_number(self):
        with self.assertRaisesRegex(ValidationError, "invented number"):
            validate_draft(payload(title="cortiq 9.9.9 agrega backend"), SOURCE)

    def test_rejects_ungrounded_quote(self):
        with self.assertRaisesRegex(ValidationError, "not grounded"):
            validate_draft(payload(source_quote="CUDA desaparece en 0.8.67"), SOURCE)

    def test_rejects_inverted_negation(self):
        source = "The engine does not support CUDA on this card."
        bad = payload(
            title="El motor soporta CUDA",
            affects="motor CUDA",
            source_quote="does not support CUDA",
        )
        with self.assertRaisesRegex(ValidationError, "negation inverted"):
            validate_draft(bad, source)

    def test_rejects_duplicate_ids(self):
        import json

        duplicate = {"items": [payload()["items"][0], payload()["items"][0]]}
        with self.assertRaisesRegex(ValidationError, "Duplicate id"):
            validate_draft(duplicate, SOURCE)

    def test_rejects_empty_items(self):
        with self.assertRaisesRegex(ValidationError, "1 to"):
            validate_draft({"items": []}, SOURCE)

    def test_drops_duplicate_quote_with_warning(self):
        import json

        second = payload()["items"][0].copy()
        second["id"] = "C2"
        raw = {"items": [payload()["items"][0], second]}
        outcome = validate_draft(raw, SOURCE)
        self.assertEqual(len(outcome.items), 1)
        self.assertTrue(any("duplicate" in w for w in outcome.warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
