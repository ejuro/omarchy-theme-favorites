#!/usr/bin/env python3
"""Prepare private image export files."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
import stat


def export_directory():
    pictures = Path.home() / 'Pictures'
    try:
        result = subprocess.run(['xdg-user-dir', 'PICTURES'], capture_output=True, text=True, timeout=2)
        candidate = Path(result.stdout.strip())
        if result.returncode == 0 and candidate.is_absolute():
            pictures = candidate
    except (OSError, subprocess.TimeoutExpired):
        pass
    return pictures / 'Theme Favorites'


def prepare(directory=None):
    directory = directory or export_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='theme-favorites-' + dt.date.today().isoformat() + '-',
                                suffix='.png', dir=directory)
    os.close(fd)
    return name


def discard_empty(name, directory=None):
    directory = directory or export_directory()
    path = Path(name)
    if path.parent != directory or not path.name.startswith('theme-favorites-') or path.suffix != '.png':
        return
    try:
        info = path.lstat()
        if stat.S_ISREG(info.st_mode) and info.st_size == 0:
            path.unlink()
    except FileNotFoundError:
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'discard-empty'])
    parser.add_argument('path', nargs='?', default='')
    args = parser.parse_args()
    try:
        if args.action == 'discard-empty':
            discard_empty(args.path)
        else:
            print(json.dumps({'path': prepare()}))
    except (OSError, ValueError, subprocess.SubprocessError):
        print(json.dumps({'error': 'Could not prepare the image.'}))
        raise SystemExit(1)
