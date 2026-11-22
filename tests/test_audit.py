import unittest

from src.audit import build_payload, run_audit
from src.config import SKILL_AUDIT_SCRIPT
from src.domain import ChecklistItem, ChecklistResult, GenerationError, SourceDocument, SourceLine


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.source = SourceDocument(
            name="release_notes.txt",
            url="https://example.invalid/notes",
            lines=(SourceLine(1, "cortiq 0.8.67 adds a native CUDA backend."),),
        )
        self.result = ChecklistResult(
            source_name=self.source.name,
            items=(
                ChecklistItem(
                    id="C1",
                    title="cortiq 0.8.67 agrega backend CUDA",
                    affects="motor CUDA",
                    source_quote="cortiq 0.8.67 adds a native CUDA backend",
                    breaking=False,
                ),
            ),
            raw_output="",
        )

    def test_payload_matches_skill_contract(self):
        payload = build_payload(self.result, self.source)
        self.assertIn("answer", payload)
        self.assertEqual(payload["mode"], "local")
        self.assertEqual(len(payload["sources"]), len(self.source.lines))
        self.assertEqual(payload["sources"][0]["metadata"]["line_start"], 1)
        self.assertEqual(payload["sources"][0]["content"], self.source.lines[0].text)
        self.assertNotIn("source_quote", payload)

    @unittest.skipUnless(SKILL_AUDIT_SCRIPT.is_file(), "SkillHub skill not installed")
    def test_skill_produces_contract_report(self):
        report = run_audit(build_payload(self.result, self.source))
        self.assertIn(report["status"], {"complete", "partial", "refused"})
        self.assertIsInstance(report["claims"], list)
        self.assertIsInstance(report["sources"], list)

    def test_empty_sources_are_rejected(self):
        with self.assertRaisesRegex(GenerationError, "no evidence sources"):
            run_audit({"answer": "x", "sources": []})


if __name__ == "__main__":
    unittest.main(verbosity=2)
