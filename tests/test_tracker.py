import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tracker


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "history.sqlite3"
        self.start = dt.datetime(2026, 9, 17, 12, tzinfo=dt.timezone.utc).timestamp()
        self.history = tracker.History(self.path, self.start, dt.timezone.utc)

    def tearDown(self):
        self.history.db.close()
        self.tmp.cleanup()

    def sample(self, offset, theme="ash", active=True, mono=None, boot=None):
        self.history.sample(self.start + offset, offset if mono is None else mono,
                            offset if boot is None else boot, theme, active)

    def rows(self, offset=100, period="all"):
        return self.history.snapshot(self.start + offset)["periods"][period]

    def test_retained_theme_beats_frequently_selected_theme(self):
        self.sample(0)
        for offset in range(5, 65, 5):
            self.sample(offset)
        self.sample(65, "nord")
        self.sample(70, "ash")
        self.sample(75, "nord")
        self.sample(80, "ash")
        rows = self.rows()
        self.assertEqual(rows[0]["slug"], "ash")
        self.assertEqual(rows[0]["seconds"], 70)
        self.assertEqual(rows[1]["selections"], 2)

    def test_same_theme_does_not_increment_count(self):
        self.sample(0)
        self.sample(5)
        self.sample(10)
        self.assertEqual(self.rows()[0]["selections"], 0)
        self.assertEqual(self.history.db.execute("SELECT COUNT(*) FROM spans").fetchone()[0], 1)

    def test_lock_and_unknown_state_are_excluded(self):
        self.sample(0)
        self.sample(5)
        self.sample(10, active=False)
        self.sample(15, active=False)
        self.sample(20, active=True)
        self.sample(25)
        self.sample(30, active=None)
        self.sample(35)
        self.sample(40)
        self.assertEqual(self.rows()[0]["seconds"], 15)

    def test_suspend_and_clock_adjustments_do_not_create_usage(self):
        self.sample(0)
        self.sample(5)
        self.sample(3605, mono=10, boot=3605)
        self.sample(3610, mono=15, boot=3610)
        self.sample(7200, mono=20, boot=3615)
        self.assertEqual(self.rows(7300)[0]["seconds"], 10)

    def test_short_suspend_is_also_excluded(self):
        self.sample(0)
        self.sample(5, mono=2, boot=5)
        self.assertEqual(self.rows(), [])

    def test_long_process_stall_is_not_backfilled(self):
        self.sample(0)
        self.sample(5)
        self.sample(120)
        self.sample(125)
        self.assertEqual(self.rows(130)[0]["seconds"], 10)

    def test_restart_preserves_start_date_but_never_backfills(self):
        self.sample(0)
        self.sample(5)
        original_date = self.history.snapshot(self.start)["since"]
        self.history.db.close()
        self.history = tracker.History(self.path, self.start + 86400)
        self.sample(86400, "nord")
        self.sample(86405, "nord")
        self.assertEqual(sum(row["seconds"] for row in self.rows(86410)), 10)
        self.assertEqual(sum(row["selections"] for row in self.rows(86410)), 0)
        self.assertEqual(self.history.snapshot(self.start + 86410)["since"], original_date)

    def test_partial_theme_file_does_not_invent_selection(self):
        self.sample(0)
        self.sample(5, "")
        self.sample(6)
        self.sample(11)
        self.assertEqual(self.rows()[0]["selections"], 0)
        self.assertEqual(self.rows()[0]["seconds"], 5)

    def test_periods_clip_spans_at_midnight_and_count_only_period_selections(self):
        self.history.zone = ZoneInfo("Europe/Stockholm")
        now = dt.datetime(2026, 6, 1, 0, 0, 5, tzinfo=self.history.zone).timestamp()
        self.history.sample(now - 10, 0, 0, "ash", True)
        self.history.sample(now, 10, 10, "nord", True)
        self.history.sample(now + 5, 15, 15, "nord", True)
        snapshot = self.history.snapshot(now + 5)
        for key in ("week", "month"):
            self.assertEqual(sum(row["seconds"] for row in snapshot["periods"][key]), 10)
        self.assertEqual(sum(row["seconds"] for row in snapshot["periods"]["all"]), 15)
        self.assertEqual(snapshot["periods"]["week"][1]["selections"], 1)

    def test_calendar_boundaries_use_dst_offset_at_boundary(self):
        zone = ZoneInfo("Europe/Stockholm")
        now = dt.datetime(2026, 3, 30, 10, tzinfo=zone).timestamp()
        starts = tracker.boundaries(now, zone)
        self.assertEqual(starts["month"], dt.datetime(2026, 2, 28, 23, tzinfo=dt.timezone.utc).timestamp())
        self.assertEqual(starts["week"], dt.datetime(2026, 3, 29, 22, tzinfo=dt.timezone.utc).timestamp())

    def test_year_boundary_retains_all_ranked_themes(self):
        now = dt.datetime(2027, 1, 1, 0, 0, 5, tzinfo=dt.timezone.utc).timestamp()
        for index in range(7):
            with self.history.db:
                self.history.db.execute("INSERT INTO spans(theme,start,end) VALUES(?,?,?)",
                                        (f"theme-{index}", now - 10 - index, now))
        snapshot = self.history.snapshot(now)
        self.assertEqual(len(snapshot["periods"]["all"]), 7)
        self.assertEqual(snapshot["periods"]["all"][0]["slug"], "theme-6")
        self.assertEqual(snapshot["periods"]["all"][-1]["slug"], "theme-0")
        self.assertTrue(all(row["seconds"] == 5 for row in snapshot["periods"]["year"]))


class MetadataTests(unittest.TestCase):
    def test_bundled_credit_survives_palette_overlay_but_user_creator_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "stock/nord").mkdir(parents=True)
            (base / "themes/nord").mkdir(parents=True)
            result = tracker.metadata("nord", base, base / "stock")
            self.assertEqual(result["credit"], "Created by DHH")
            self.assertEqual(result["url"], "https://github.com/omacom/omarchy/tree/master/themes/nord")
            self.assertEqual(result["palette_credit"], "Original color scheme by Sven Greb")
            result = tracker.metadata("nord", base, base / "stock", {"nord": {"creator": "Custom creator"}})
            self.assertEqual(result["credit"], "Created by Custom creator")

    @patch("tracker.subprocess.run")
    def test_same_named_git_theme_does_not_receive_stock_attribution(self, run):
        run.return_value.stdout = "https://github.com/custom-owner/nord.git\n"
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "stock/nord").mkdir(parents=True)
            (base / "themes/nord/.git").mkdir(parents=True)
            result = tracker.metadata("nord", base, base / "stock")
            self.assertEqual(result["credit"], "Created by @custom-owner")
            self.assertEqual(result["palette_credit"], "")
            self.assertEqual(result["url"], "https://github.com/custom-owner/nord")

    def test_normalizes_github_remotes_without_credentials(self):
        for raw in ("git@github.com:owner/theme.git", "https://github.com/owner/theme.git",
                    "ssh://git@github.com/owner/theme.git", "https://user:secret@github.com/owner/theme"):
            self.assertEqual(tracker.github_url(raw), "https://github.com/owner/theme")
        for raw in ("file:///etc/passwd", "https://github.com.evil.example/o/r", "javascript:alert(1)"):
            self.assertEqual(tracker.github_url(raw), "")

    def test_explicit_author_overrides_repository_owner_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            theme = base / "themes" / "ash"
            theme.mkdir(parents=True)
            (theme / "theme.json").write_text(json.dumps({"repository": "https://github.com/forker/ash"}))
            result = tracker.metadata("ash", base, base / "stock")
            self.assertEqual(result["credit"], "Created by @forker")
            result = tracker.metadata("ash", base, base / "stock", {"ash": {"author": "Original creator"}})
            self.assertEqual(result["credit"], "Created by Original creator")

    def test_overlay_inherits_stock_palette_and_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            custom, stock = base / "themes/ash", base / "stock/ash"
            custom.mkdir(parents=True)
            stock.mkdir(parents=True)
            (stock / "colors.toml").write_text('background = "#000000"\naccent = "#ffffff"\n')
            (custom / "colors.toml").write_text('accent = "#112233"\n')
            (stock / "preview.png").touch()
            result = tracker.metadata("ash", base, base / "stock")
            self.assertEqual(result["palette"], ["#000000", "#112233"])
            self.assertTrue(result["preview"].endswith("preview.png"))

    @patch("tracker.subprocess.run")
    def test_lock_detection_fails_closed(self, run):
        run.return_value.returncode = 0
        for monitors, expected in [([], None), ([{}], None),
                                   ([{"solitaryBlockedBy": ["LOCK"], "dpmsStatus": True}], False),
                                   ([{"solitaryBlockedBy": [], "dpmsStatus": False}], False),
                                   ([{"solitaryBlockedBy": ["WORKSPACE"], "dpmsStatus": True}], None),
                                   ([{"solitaryBlockedBy": [], "dpmsStatus": True}], True)]:
            run.return_value.stdout = json.dumps(monitors)
            self.assertIs(tracker.active_desktop(), expected)


if __name__ == "__main__":
    unittest.main()
