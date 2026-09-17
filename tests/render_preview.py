#!/usr/bin/env python3
"""Render sample stats through the real shell components, isolated from history."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tracker

artifacts = ROOT / "tests/artifacts"
artifacts.mkdir(exist_ok=True)
themes = ["tokyo-night", "catppuccin", "nord", "gruvbox", "ash"]
rows = [tracker.metadata(slug) | {"seconds": seconds, "selections": count}
        for slug, seconds, count in zip(themes, [67320, 44400, 29100, 14700, 4200], [6, 4, 3, 2, 1])]
extra_rows = [tracker.metadata(slug) | {"seconds": seconds, "selections": 1}
              for slug, seconds in [("everforest", 3600), ("rose-pine", 1800), ("kanagawa", 900)]]
snapshot = {"since": "2026.09.17", "status": "tracking", "current": "tokyo-night",
            "periods": {"week": rows, "month": list(reversed(rows)), "year": rows[:2], "all": rows + extra_rows}}
with tempfile.TemporaryDirectory(prefix="theme-favorites-preview-") as tmp:
    tmp = Path(tmp)
    shell = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
    for name in ("Ui", "Commons"):
        (tmp / name).symlink_to(shell / name, target_is_directory=True)
    (tmp / "Plugin").symlink_to(ROOT, target_is_directory=True)
    (tmp / "runtime").mkdir(mode=0o700)
    qml = '''import QtQuick
import Quickshell
import qs.Commons
import "PLUGIN" as Favorites
ShellRoot {
    Favorites.Service { id: service }
    FloatingWindow {
        id: win
        visible: true
        implicitWidth: content.width + 40
        implicitHeight: content.implicitHeight + 40
        color: Color.popups.background
        Rectangle {
          id: card
          width: content.width + 40
          height: content.implicitHeight + 40
          color: Color.popups.background
          Favorites.FavoritesContent {
            id: content
            x: 20; y: 20
            width: Style.space(440)
            snapshot: SNAPSHOT
          }
        }
    }
    Timer {
        interval: 1500; running: true
        onTriggered: {
            if (!service.snapshot.since || service.lastError) throw new Error("Tracker service failed: " + service.lastError)
            service.refresh()
            if (content.rows.length !== 5) throw new Error("Expected top five")
            content.changePeriod(1)
            if (content.rows[0].slug !== "ash") throw new Error("Month did not update rows")
            content.changePeriod(1)
            if (content.rows.length !== 2) throw new Error("Year did not update rows")
            content.changePeriod(2)
            if (content.rows[0].slug !== "tokyo-night") throw new Error("Week did not restore")
            if (content.duration(67320) !== "18h 42m") throw new Error("Duration formatting")
            content.selectedPeriod = 3
            scrollCheck.start()
        }
    }
    Timer {
        id: scrollCheck
        interval: 100
        onTriggered: {
            if (content.rows.length !== 8) throw new Error("All themes must be available")
            if (content.listHeight !== content.rowHeight * 5) throw new Error("List must show five rows")
            var footerY = content.footerY
            for (var i = 0; i < 8; i++) content.changeRow(1)
            if (content.scrollPosition <= 0) throw new Error("Keyboard selection must scroll to row eight")
            if (content.footerY !== footerY) throw new Error("Footer must stay pinned")
            var offset = content.scrollPosition
            var refreshed = JSON.parse(JSON.stringify(content.snapshot))
            refreshed.periods.all[0].seconds += 5
            content.snapshot = refreshed
            if (content.scrollPosition !== offset) throw new Error("Usage refresh must preserve scroll position")
            content.availableHeight = content.preferredHeight - content.rowHeight
            if (content.listHeight !== content.rowHeight * 4) throw new Error("Small screens must shrink only the list")
            content.availableHeight = 0
            var many = []
            for (var n = 0; n < 1000; n++) {
                var row = JSON.parse(JSON.stringify(content.rows[0]))
                row.slug = "stress-" + n
                row.name = "Long theme name " + n + " with extra descriptive words"
                row.seconds = 10 * 365 * 86400 + 42 * 86400
                many.push(row)
            }
            content.snapshot = {since: "2016.09.17", status: "tracking", periods: {all: many, year: many.slice(0, 2)}}
            stressCheck.start()
        }
    }
    Timer {
        id: stressCheck
        interval: 100
        onTriggered: {
            if (content.rankedRows.length !== 1000 || content.rows.length !== 20) throw new Error("Top 20 limit must preserve complete ranking")
            for (var i = 0; i < 1100; i++) content.changeRow(1)
            if (content.selectedRow !== 19) throw new Error("Large library keyboard bounds")
            if (content.listHeight !== content.rowHeight * 5) throw new Error("Large library expanded panel")
            if (content.duration(10 * 365 * 86400 + 42 * 86400) !== "10y 42d") throw new Error("Long duration formatting")
            if (content.duration(86400 + 3600) !== "1d 1h") throw new Error("Day duration formatting")
            content.selectedPeriod = 2
            if (content.selectedRow !== -1 || content.rows.length !== 2) throw new Error("Large to small period transition")
            content.snapshot = SNAPSHOT
            content.selectedPeriod = 0
            captureTimer.start()
        }
    }
    Timer {
        id: captureTimer
        interval: 100
        onTriggered: {
            card.grabToImage(function(result) {
                if (!result.saveToFile("OUTPUT")) throw new Error("Could not save preview")
                content.selectedPeriod = 0
                if (content.scrollPosition !== 0) throw new Error("Changing periods must reset scrolling")
                console.log("PASS: period tabs, all themes, scrolling, pinned footer, live refresh, small screens, 1000 themes, long durations and rendering")
                Qt.quit()
            })
        }
    }
}'''.replace("PLUGIN", "Plugin").replace("SNAPSHOT", json.dumps(snapshot)).replace("OUTPUT", str(artifacts / "preview.png"))
    (tmp / "shell.qml").write_text(qml)
    env = os.environ | {"QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                        "QT_QPA_PLATFORMTHEME": "generic", "QT_QUICK_CONTROLS_STYLE": "Basic",
                        "XDG_RUNTIME_DIR": str(tmp / "runtime"), "XDG_STATE_HOME": str(tmp / "state")}
    try:
        result = subprocess.run(["quickshell", "--no-color", "-p", str(tmp / "shell.qml")],
                                env=env, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired as error:
        print((error.stdout or b"").decode())
        print((error.stderr or b"").decode())
        raise SystemExit("Preview timed out")
    log = result.stdout + result.stderr
    (artifacts / "preview.log").write_text(log)
    print(log)
    if result.returncode or "PASS:" not in log or any(word in log for word in ("ReferenceError", "TypeError", "Unable to assign", "Failed to load")):
        raise SystemExit(1)
print(artifacts / "preview.png")
