import unittest

from src.domain import ChecklistItem, ChecklistResult, Review, build_exports, is_approved


def result():
    return ChecklistResult(
        source_name="notes.txt",
        items=(
            ChecklistItem("C1", "a", "x", "line one", False, 1, 1),
            ChecklistItem("C2", "b", "y", "line two", False, 2, 2),
            ChecklistItem("C3", "c", "z", "line three", False, 3, 3),
        ),
        raw_output="",
    )


class ApprovalTests(unittest.TestCase):
    def test_no_review_is_not_approved(self):
        self.assertFalse(is_approved(None))

    def test_pending_is_not_approved(self):
        self.assertFalse(is_approved(Review("pending")))

    def test_explicit_accept_is_approved(self):
        self.assertTrue(is_approved(Review("accept")))

    def test_empty_correction_is_not_approved(self):
        self.assertFalse(is_approved(Review("correct", "   ")))

    def test_correction_with_text_is_approved(self):
        self.assertTrue(is_approved(Review("correct", "Use 8 192 tokens")))

    def test_reject_is_not_approved(self):
        self.assertFalse(is_approved(Review("reject")))


    def test_exports_separate_approved_from_full_log(self):
        reviews = {
            "C1": Review("accept"),
            "C2": Review("reject"),
            "C3": Review("pending"),
        }
        final, log = build_exports(result(), reviews)
        self.assertEqual([i["id"] for i in final["approved"]], ["C1"])
        self.assertEqual([i["id"] for i in log["items"]], ["C1", "C2", "C3"])
        self.assertEqual([i["decision"] for i in log["items"]], ["accept", "reject", "pending"])
        self.assertEqual([i["approved"] for i in log["items"]], [True, False, False])
        self.assertTrue(all("generated_title" in i for i in log["items"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
