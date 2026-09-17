"""Regression checks for local metadata, private storage and installer behavior."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tracker


class SecurityTests(unittest.TestCase):
    def test_malformed_and_unsafe_repository_urls_are_rejected(self):
        for value in ('https://[github.com/o/r', 'https://github.com/../r',
                      'https://github.com/o/.', 'https://github.com/o/r/../../evil',
                      'https://github.com@evil.test/o/r', 'file:///tmp/run.desktop',
                      'javascript:alert(1)', 'https://github.com/o/r;touch-pwned'):
            with self.subTest(value=value):
                self.assertEqual(tracker.github_url(value), '')

    def test_bad_optional_metadata_does_not_stop_tracking(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            theme = base / 'themes/demo'
            theme.mkdir(parents=True)
            (theme / 'colors.toml').write_bytes(b'\xff')
            (theme / 'theme.json').write_text(json.dumps({'repository': 'https://[broken'}))
            result = tracker.metadata('demo', base, base / 'stock')
            self.assertEqual(result['url'], '')
            self.assertEqual(result['palette'], [])
            (theme / 'theme.json').write_bytes(b'x' * 262145)
            self.assertEqual(tracker.metadata('demo', base, base / 'stock')['credit'], 'Creator not listed')

    def test_bad_current_theme_is_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'theme.name'
            with patch.object(tracker, 'CURRENT', path):
                for data in (b'\xff', b'../../outside', b'a' * 256):
                    path.write_bytes(data)
                    self.assertEqual(tracker.theme_name(), '')

    def test_state_permissions_and_atomic_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / 'state'
            state.mkdir(mode=0o755)
            for name in ('history.sqlite3', 'snapshot.json', 'tracker.lock'):
                (state / name).write_text('old')
                (state / name).chmod(0o644)
            old_mask = os.umask(0o022)
            try:
                tracker.prepare_state(state)
                tracker.write_snapshot(state, '{"status":"tracking"}')
                self.assertEqual(state.stat().st_mode & 0o777, 0o700)
                for path in state.iterdir():
                    self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads((state / 'snapshot.json').read_text())['status'], 'tracking')
                self.assertFalse(list(state.glob('.snapshot-*')))
            finally:
                os.umask(old_mask)

    def test_installer_is_repeatable_and_preserves_existing_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            config, state, bins = base / 'config', base / 'state', base / 'bin'
            bins.mkdir()
            for name in ('omarchy', 'omarchy-shell'):
                script = bins / name
                script.write_text('#!/bin/sh\nexit 0\n')
                script.chmod(0o755)
            (config / 'omarchy').mkdir(parents=True)
            (config / 'omarchy/shell.json').write_text('{"existing":true}')
            env = os.environ | {'XDG_CONFIG_HOME': str(config), 'XDG_STATE_HOME': str(state),
                                'PATH': str(bins) + os.pathsep + os.environ['PATH']}
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'install.sh')], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            backups = list((state / 'theme-favorites/backups').glob('*.json'))
            self.assertEqual(len(backups), 2)
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in backups))
            self.assertEqual((state / 'theme-favorites').stat().st_mode & 0o777, 0o700)
            target = config / 'omarchy/plugins/io.github.ejuro.theme-favorites'
            self.assertEqual(target.resolve(), ROOT)
            target.unlink()
            target.mkdir()
            sentinel = target / 'keep'
            sentinel.write_text('existing installation')
            result = subprocess.run(['bash', str(ROOT / 'install.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(sentinel.read_text(), 'existing installation')
