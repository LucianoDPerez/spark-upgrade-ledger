import unittest

from src.domain import Review, is_approved


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
