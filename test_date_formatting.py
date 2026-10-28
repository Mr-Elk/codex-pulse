"""Chinese date labels must work in Windows' default C time locale."""
from datetime import datetime
import locale
import unittest

from product_data import moment
from quota_model import clock_text
from quota_records import record_range


class DateFormattingTests(unittest.TestCase):
    def setUp(self):
        previous = locale.setlocale(locale.LC_TIME)
        self.addCleanup(locale.setlocale, locale.LC_TIME, previous)
        locale.setlocale(locale.LC_TIME, "C")

    def test_local_date_labels_in_non_chinese_locale(self):
        stamp = datetime(2026, 1, 2, 3, 4, 5).timestamp()
        self.assertEqual(moment(stamp), "01月02日 03:04")
        self.assertEqual(clock_text(stamp), "01 月 02 日 03:04")

    def test_same_minute_and_cross_day_ranges_keep_their_precision(self):
        start = datetime(2026, 1, 2, 3, 4, 5).timestamp()
        self.assertEqual(record_range({'start': start, 'at': start + 30}),
                         "01月02日 03:04:05 – 03:04:35")
        start = datetime(2026, 1, 2, 23, 59).timestamp()
        end = datetime(2026, 1, 3, 0, 1).timestamp()
        self.assertEqual(record_range({'start': start, 'at': end}),
                         "01月02日 23:59 – 01月03日 00:01")

    def test_missing_timestamps_keep_their_existing_labels(self):
        for stamp in (None, 0, -1):
            with self.subTest(stamp=stamp):
                self.assertEqual(moment(stamp), "尚无记录")
                self.assertEqual(clock_text(stamp), "暂未提供")


if __name__ == "__main__":
    unittest.main()
