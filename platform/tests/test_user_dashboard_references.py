import unittest

from app.user_dashboard.service import _luke_chapter_from_reference


class UserDashboardReferenceTests(unittest.TestCase):
    def test_accepts_named_and_pipeline_references(self):
        self.assertEqual(_luke_chapter_from_reference("Luke 1:11"), 1)
        self.assertEqual(_luke_chapter_from_reference("1:11"), 1)
        self.assertEqual(_luke_chapter_from_reference("1:35(#2)"), 1)

    def test_rejects_unknown_reference(self):
        self.assertIsNone(_luke_chapter_from_reference("Unknown passage"))


if __name__ == "__main__":
    unittest.main()
