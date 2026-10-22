import unittest

from active_chat import Binding

CATALOG = [{"id":"a","title":"对话 A"},{"id":"b","title":"对话 B"}]


class FollowingTests(unittest.TestCase):
    def test_follows_visible_title_instead_of_catalog_recency(self):
        binding=Binding().follow("对话 B",CATALOG)
        self.assertEqual(binding.identity,"b")
        after=binding.follow("对话 A",CATALOG)
        self.assertEqual(after.identity,"a")
        self.assertGreater(after.revision,binding.revision)

    def test_duplicates_missing_and_failed_probes_never_keep_old_binding(self):
        binding=Binding().follow("对话 A",CATALOG)
        for title,catalog,status,expected in (
            ("对话 A",CATALOG+[{"id":"c","title":"对话 A"}],"ok","ambiguous"),
            ("新对话",CATALOG,"ok","not_found"),
            (None,CATALOG,"unavailable","unavailable")):
            with self.subTest(status=expected):
                after=binding.follow(title,catalog,status)
                self.assertIsNone(after.identity)
                self.assertEqual(after.status,expected)
                self.assertFalse(after.accepts("a",binding.revision))

    def test_returning_to_same_chat_rejects_results_from_previous_visit(self):
        first=Binding().follow("对话 A",CATALOG)
        returned=first.follow("对话 B",CATALOG).follow("对话 A",CATALOG)
        self.assertFalse(returned.accepts("a",first.revision))
        self.assertTrue(returned.accepts("a",returned.revision))

    def test_fixed_mode_ignores_navigation_and_auto_can_be_restored(self):
        fixed=Binding().pin("a","对话 A")
        self.assertEqual(fixed.follow("对话 B",CATALOG),fixed)
        self.assertEqual(fixed.automatic().follow("对话 B",CATALOG).identity,"b")

    def test_unchanged_title_does_not_discard_new_metrics(self):
        binding=Binding().follow("对话 A",CATALOG)
        self.assertIs(binding.follow("对话 A",CATALOG),binding)
        self.assertIsNone(Binding().identity)


if __name__ == "__main__":
    unittest.main()
