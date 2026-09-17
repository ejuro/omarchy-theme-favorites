import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import share


class ShareTests(unittest.TestCase):
    def test_discard_only_empty_exports(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            empty = Path(share.prepare(directory))
            saved = Path(share.prepare(directory))
            saved.write_bytes(b'keep image')
            unrelated = directory / 'other.png'
            unrelated.touch()
            link = directory / 'theme-favorites-link.png'
            link.symlink_to(unrelated)
            for path in (empty, saved, unrelated, link):
                share.discard_empty(str(path), directory)
            self.assertFalse(empty.exists())
            self.assertEqual(saved.read_bytes(), b'keep image')
            self.assertTrue(unrelated.exists())
            self.assertTrue(link.is_symlink())

    def test_unique_private_files(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d) / 'Pictures with spaces'
            first, second = share.prepare(directory), share.prepare(directory)
            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).stat().st_mode & 0o777, 0o600)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)

    @patch('share.subprocess.run', side_effect=subprocess.TimeoutExpired('xdg-user-dir', 2))
    def test_pictures_lookup_failure_has_fallback(self, run):
        self.assertEqual(share.export_directory(), Path.home() / 'Pictures/Theme Favorites')
