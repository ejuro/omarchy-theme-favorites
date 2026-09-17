"""Long histories and large libraries, without touching real usage data."""
import datetime as dt
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tracker


class ScaleTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2036, 9, 17, 12, tzinfo=dt.timezone.utc).timestamp()
        self.h = tracker.History(':memory:', self.now - 10 * 365 * 86400, dt.timezone.utc)

    def tearDown(self):
        self.h.db.close()

    def test_ten_years_of_daily_use_has_exact_totals(self):
        # Ten years of eight-hour days, not uninterrupted elapsed calendar time.
        with self.h.db:
            self.h.db.executemany('INSERT INTO spans(theme,start,end) VALUES(?,?,?)',
                                 [('favorite', self.now - day * 86400 - 28800,
                                   self.now - day * 86400) for day in range(3650)])
        report = self.h.snapshot(self.now)
        self.assertEqual(report['periods']['all'][0]['seconds'], 3650 * 28800)
        for key, start in tracker.boundaries(self.now, dt.timezone.utc).items():
            expected = sum(max(0, min(self.now - day * 86400, self.now) -
                               max(self.now - day * 86400 - 28800, start)) for day in range(3650))
            self.assertEqual(report['periods'][key][0]['seconds'], expected)

    def test_thousand_themes_are_ranked_without_losing_history(self):
        with self.h.db:
            self.h.db.executemany('INSERT INTO spans(theme,start,end) VALUES(?,?,?)',
                                 [(f'theme-{i:04}', self.now - (i + 1) * 1000,
                                   self.now - (i + 1) * 1000 + i + 1) for i in range(1000)])
        rows = self.h.snapshot(self.now)['periods']['all']
        self.assertEqual(len(rows), 1000)
        self.assertEqual(rows[0]['slug'], 'theme-0999')
        self.assertEqual(rows[-1]['slug'], 'theme-0000')
        self.assertEqual(sum(row['seconds'] for row in rows), 500500)

    def test_day_of_heartbeats_coalesces_without_rounding_drift(self):
        for offset in range(0, 86401, 5):
            self.h.sample(self.now - 86400 + offset, offset, offset, 'favorite', True)
        self.assertEqual(self.h.snapshot(self.now)['periods']['all'][0]['seconds'], 86400)
        self.assertEqual(self.h.db.execute('SELECT COUNT(*) FROM spans').fetchone()[0], 1)

    def test_many_equal_rankings_are_stable(self):
        with self.h.db:
            self.h.db.executemany('INSERT INTO spans(theme,start,end) VALUES(?,?,?)',
                                 [(f'theme-{i:04}', self.now - 100, self.now) for i in reversed(range(1000))])
        rows = self.h.snapshot(self.now)['periods']['all']
        self.assertEqual([row['slug'] for row in rows], [f'theme-{i:04}' for i in range(1000)])
