#!/usr/bin/env python3
"""Local theme history. Python standard library only; no network requests."""
import argparse
import ctypes
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import select
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

INTERVAL = 5
HOME = Path.home()
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "omarchy"
STATE = Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "theme-favorites"
# Omarchy itself currently uses this path independently of XDG_STATE_HOME.
CURRENT = HOME / ".local/state/omarchy/current/theme.name"
STOCK = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "themes"


def local_zone():
    try:
        if os.environ.get("TZ"):
            return ZoneInfo(os.environ["TZ"].lstrip(":"))
        with open("/etc/localtime", "rb") as stream:
            return ZoneInfo.from_file(stream)
    except (OSError, ValueError, KeyError):
        return dt.timezone.utc


def boundaries(now, zone):
    today = dt.datetime.fromtimestamp(now, zone).date()
    dates = {"week": today - dt.timedelta(days=today.weekday()),
             "month": today.replace(day=1), "year": today.replace(month=1, day=1)}
    return {key: dt.datetime.combine(day, dt.time(), zone).timestamp()
            for key, day in dates.items()} | {"all": 0}


def github_url(raw):
    """Normalize repository remotes; never expose credentials or arbitrary schemes."""
    raw = str(raw or "").strip()
    if raw.startswith("git@github.com:"):
        raw = "https://github.com/" + raw[len("git@github.com:"):]
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    if parsed.hostname != "github.com" or parsed.scheme not in ("https", "ssh") or parsed.params:
        return ""
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in (".", "..") for part in parts):
        return ""
    return "https://github.com/" + "/".join(parts)


def read_text(path, limit=262144):
    """Keep optional local metadata bounded and tolerate broken theme files."""
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Theme metadata exceeds size limit")
    return data.decode("utf-8")


def read_json(path):
    try:
        value = json.loads(read_text(path))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


BUILTIN_THEMES = read_json(Path(__file__).with_name("builtin-themes.json"))


def metadata(slug, config=CONFIG, stock=STOCK, overrides=None):
    name = slug.replace("-", " ").replace("_", " ").title()
    result = {"slug": slug, "name": name, "credit": "Creator not listed",
              "url": "", "preview": "", "palette": [], "palette_credit": ""}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", slug) or ".." in slug:
        return result
    custom = config / "themes" / slug
    bundled = stock / slug
    roots = [p for p in (custom, bundled) if p.is_dir()]
    # Overlay palettes inherit missing keys from stock.
    colors = {}
    # Small user palette overlays inherit the original theme's attribution.
    # An independently cloned theme with the same slug keeps its own metadata.
    builtin = BUILTIN_THEMES.get(slug, {}) if bundled.is_dir() and not (custom / ".git").exists() else {}
    info = {}
    for path in reversed(roots):
        try:
            colors.update(tomllib.loads(read_text(path / "colors.toml")))
        except (OSError, ValueError):
            pass
        info.update(read_json(path / "theme.json"))
        info.update(read_json(path / "theme-favorites.json"))
    if overrides is not None:
        override = overrides.get(slug, {})
        if isinstance(override, dict):
            info.update(override)
    for key in ("background", "accent", "red", "green", "blue", "foreground"):
        color = colors.get(key, "")
        if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            if color not in result["palette"]:
                result["palette"].append(color)
    url = github_url(info.get("repository", info.get("url", "")))
    if not url:
        url = github_url(builtin.get("repository", ""))
    if not url and custom.is_dir() and (custom / ".git").exists():
        try:
            remote = subprocess.run(["git", "-C", str(custom), "config", "--get", "remote.origin.url"],
                                    capture_output=True, text=True, timeout=2, check=False)
            url = github_url(remote.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass
    author = info.get("author", info.get("creator", builtin.get("author", "")))
    if isinstance(author, dict):
        author = author.get("name", "")
    if isinstance(author, str) and author.strip():
        result["credit"] = "Created by " + author.strip()[:120]
    elif url:
        # Explicit creator metadata takes precedence over the repository fallback.
        result["credit"] = "Created by @" + urlparse(url).path.split("/")[1]
    elif bundled.is_dir():
        result["credit"] = "Omarchy built-in"
    palette_author = info.get("palette_author", builtin.get("palette_author", ""))
    if isinstance(palette_author, str) and palette_author.strip():
        result["palette_credit"] = "Original color scheme by " + palette_author.strip()[:120]
    if not url and bundled.is_dir():
        url = "https://github.com/omacom/omarchy/tree/master/themes/" + slug
    if isinstance(info.get("name"), str) and info["name"].strip():
        result["name"] = info["name"].strip()[:120]
    result["url"] = url
    for path in roots:
        candidates = [path / n for n in ("preview.png", "theme.png", "preview.jpg", "screenshot.png")]
        backgrounds = path / "backgrounds"
        if backgrounds.is_dir():
            try:
                candidates += sorted(p for p in backgrounds.iterdir()
                                     if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
            except OSError:
                pass
        found = next((p for p in candidates if p.is_file()), None)
        if found:
            result["preview"] = found.resolve().as_uri()
            break
    return result


class History:
    def __init__(self, path, now, zone=None):
        self.zone = zone or local_zone()
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS spans
              (id INTEGER PRIMARY KEY, theme TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS spans_end ON spans(end);
            CREATE TABLE IF NOT EXISTS selections (theme TEXT NOT NULL, at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS selections_at ON selections(at);
            CREATE TABLE IF NOT EXISTS themes (slug TEXT PRIMARY KEY, metadata TEXT NOT NULL);
        """)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('started_at', ?)", (str(now),))
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('started_date', ?)",
                            (dt.datetime.fromtimestamp(now, self.zone).strftime("%Y.%m.%d"),))
        # Never resume an open interval across process restarts or disabled periods.
        self.previous = None
        self.span_id = None

    def sample(self, wall, mono, boot, theme, active):
        active = bool(active and theme)
        previous = self.previous
        changed = previous is not None and previous[3] and theme and theme != previous[3]
        with self.db:
            if previous is not None:
                old_wall, old_mono, old_boot, old_theme, old_active = previous
                elapsed = wall - old_wall
                continuous = (0 <= elapsed <= INTERVAL * 3
                              and abs(elapsed - (mono - old_mono)) < 1
                              and abs((boot - old_boot) - (mono - old_mono)) < 0.5)
                if old_active and active and old_theme and continuous and elapsed > 0:
                    if self.span_id is None:
                        cursor = self.db.execute("INSERT INTO spans(theme,start,end) VALUES(?,?,?)",
                                                 (old_theme, old_wall, wall))
                        self.span_id = cursor.lastrowid
                    else:
                        self.db.execute("UPDATE spans SET end=? WHERE id=?", (wall, self.span_id))
                else:
                    self.span_id = None
                if changed:
                    self.db.execute("INSERT INTO selections VALUES (?,?)", (theme, wall))
                    self.span_id = None
        # A transient missing/partial theme file must not invent a new selection.
        self.previous = (wall, mono, boot, theme or (previous[3] if previous else ""), active and bool(theme))

    def cache_metadata(self, slug, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO themes VALUES (?,?)", (slug, json.dumps(value)))

    def snapshot(self, now, status="tracking"):
        metadata_by_slug = {slug: json.loads(value) for slug, value in self.db.execute("SELECT * FROM themes")}
        periods = {}
        for key, start in boundaries(now, self.zone).items():
            counts = dict(self.db.execute("SELECT theme,COUNT(*) FROM selections WHERE at>=? AND at<=? GROUP BY theme",
                                          (start, now)))
            rows = self.db.execute("""SELECT theme, SUM(MIN(end,?) - MAX(start,?)) AS seconds
                FROM spans WHERE end>? AND start<? GROUP BY theme ORDER BY seconds DESC, theme ASC""",
                                   (now, start, start, now)).fetchall()
            periods[key] = [metadata_by_slug.get(slug, {"slug": slug, "name": slug, "credit": "Creator not listed",
                                                       "url": "", "preview": "", "palette": [], "palette_credit": ""})
                            | {"seconds": seconds, "selections": counts.get(slug, 0)}
                            for slug, seconds in rows if seconds > 0]
        return {"since": self.db.execute("SELECT value FROM meta WHERE key='started_date'").fetchone()[0],
                "updated_at": now,
                "periods": periods, "status": status,
                "current": self.previous[3] if self.previous else ""}


def active_desktop():
    """Use the same compositor lock indicator as omarchy-hyprland-session-locked."""
    try:
        result = subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, timeout=2)
        if result.returncode:
            return None
        monitors = json.loads(result.stdout)
        if not isinstance(monitors, list) or not monitors:
            return None
        if any("LOCK" in m.get("solitaryBlockedBy", []) for m in monitors):
            return False
        readable = [m for m in monitors if isinstance(m.get("solitaryBlockedBy"), list)
                    and "WORKSPACE" not in m["solitaryBlockedBy"]]
        return any(m.get("dpmsStatus", False) for m in readable) if readable else None
    except (OSError, ValueError, subprocess.TimeoutExpired, TypeError, AttributeError):
        return None


def theme_name():
    try:
        value = read_text(CURRENT, 255).strip()
        return value if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) and ".." not in value else ""
    except (OSError, ValueError):
        return ""


def watch_directory(path):
    """Wake on theme-file close/rename as well as the regular lock/usage heartbeat."""
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd >= 0:
        if libc.inotify_add_watch(fd, os.fsencode(path), 0x8 | 0x80 | 0x100) >= 0:
            return fd
        os.close(fd)
    return None


def prepare_state(path):
    os.umask(0o077)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    # The installer or an older version may already have created this directory.
    path.chmod(0o700)
    for name in ("history.sqlite3", "history.sqlite3-wal", "history.sqlite3-shm",
                 "snapshot.json", "tracker.lock"):
        file = path / name
        if file.is_file() and not file.is_symlink():
            file.chmod(0o600)


def write_snapshot(path, report):
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path,
                                         prefix=".snapshot-", delete=False) as stream:
            pending = Path(stream.name)
            stream.write(report)
        pending.replace(path / "snapshot.json")
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)


def watch():
    prepare_state(STATE)
    lock = (STATE / "tracker.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Theme Favorites already has a tracker running")
    history = History(STATE / "history.sqlite3", time.time())
    notify = watch_directory(CURRENT.parent)
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    cached = {}
    last_metadata = 0
    last_theme = ""
    force_metadata = True
    try:
        while running:
            current = theme_name()
            active = active_desktop()
            now, mono, boot = time.time(), time.monotonic(), time.clock_gettime(time.CLOCK_BOOTTIME)
            history.sample(now, mono, boot, current, active is True)
            if force_metadata or mono - last_metadata > 300 or current != last_theme:
                overrides = read_json(CONFIG / "theme-favorites.json")
                slugs = {row[0] for row in history.db.execute("SELECT slug FROM themes")}
                if current:
                    slugs.add(current)
                for slug in slugs:
                    details = metadata(slug, overrides=overrides)
                    # Preserve credits and links for themes subsequently uninstalled.
                    if not (CONFIG / "themes" / slug).is_dir() and not (STOCK / slug).is_dir():
                        continue
                    if details != cached.get(slug):
                        history.cache_metadata(slug, details)
                        cached[slug] = details
                last_metadata, last_theme, force_metadata = mono, current, False
            status = "tracking" if active and current else "paused" if active is False else "unavailable"
            report = json.dumps(history.snapshot(now, status), separators=(",", ":"))
            # Replacement bars intentionally have no live service lookup.
            # Share our statistics within the user's private state directory.
            write_snapshot(STATE, report)
            print(report, flush=True)
            ready, _, _ = select.select(([notify] if notify is not None else []) + [sys.stdin], [], [], INTERVAL)
            if notify is not None and notify in ready:
                os.read(notify, 65536)
            if sys.stdin in ready:
                line = sys.stdin.readline()
                if not line:  # The shell owns the process lifetime.
                    break
                force_metadata = line.strip() == "refresh"
    finally:
        if notify is not None:
            os.close(notify)
        history.db.close()
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["watch"])
    parser.parse_args()
    try:
        watch()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
