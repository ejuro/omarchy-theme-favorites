"""Exercise export in isolation; set THEME_FAVORITES_TEST_PLATFORM=wayland for desktop."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tracker
artifacts = ROOT / 'tests/artifacts'
artifacts.mkdir(exist_ok=True)
rows = [tracker.metadata(slug) | {'seconds': seconds, 'selections': 3}
        for slug, seconds in [('cool-dawn',16620), ('hackerman',7920), ('catppuccin',5100), ('last-horizon',2580), ('nord',1380)]]
snapshot = {'since':'2026.09.16','status':'tracking','periods':{'week': rows, 'month':rows[:1], 'year': [], 'all': rows}}
with tempfile.TemporaryDirectory(prefix='theme-share-test-') as tmp:
    tmp = Path(tmp)
    shell = Path(os.environ.get('OMARCHY_PATH','/usr/share/omarchy')) / 'shell'
    for name in ('Ui','Commons'): (tmp/name).symlink_to(shell/name)
    (tmp/'Plugin').symlink_to(ROOT)
    (tmp/'runtime').mkdir(mode=0o700)
    (tmp/'bin').mkdir()
    lookup=tmp/'bin/xdg-user-dir'
    lookup.write_text('#!/bin/sh\nprintf "%s\\n" "' + str(tmp/'pictures') + '"\n')
    lookup.chmod(0o755)
    qml='''import QtQuick
import Quickshell
import qs.Commons
import "Plugin" as Plugin
ShellRoot {
    FloatingWindow {
        visible: true
        implicitWidth: 513
        implicitHeight: share.preferredHeight
        Plugin.SharePanel { id: share; anchors.fill: parent }
    }
    property int stage: 0
    property int exportsDone: 0
    Timer {
        interval: 300; running: true; repeat: true
        onTriggered: {
            if (stage === 0) {
                var source = SNAPSHOT
                share.show(source, 0)
                source.periods.week[0].name = "changed after opening"
                if (share.snapshot.periods.week[0].name === "changed after opening") throw new Error("Share data must be frozen")
                stage = 1
            } else if (stage === 1) {
                share.save()
                if (share.busy) stage = 2
            } else if (stage === 2 && !share.busy) {
                if (!share.savedPath) throw new Error("Export failed: " + share.message)
                exportsDone++
                if (exportsDone === 1) {
                    share.dismiss()
                    if (share.opened || share.busy) throw new Error("Close did not reset state")
                    share.show(SNAPSHOT, 1)
                    if (!share.opened || share.selectedPeriod !== 1) throw new Error("Reopen failed")
                    stage = 1
                    return
                }
                share.save()
                share.dismiss()
                share.show(SNAPSHOT, 0)
                if (share.busy || !share.opened) throw new Error("Close during export prevented reopening")
                stage = 3
            } else if (stage === 3) {
                stage = 4
            } else if (stage === 4) {
                console.log("PASS: compact preview, export, close/reopen, repeated export and close during export")
                Qt.quit()
            }
        }
    }
}'''.replace('SNAPSHOT',json.dumps(snapshot))
    (tmp/'shell.qml').write_text(qml)
    platform = os.environ.get('THEME_FAVORITES_TEST_PLATFORM', 'offscreen')
    env=os.environ | {'QT_QPA_PLATFORM':platform,'QT_QUICK_BACKEND':'software',
                       'QT_QPA_PLATFORMTHEME':'generic','QT_QUICK_CONTROLS_STYLE':'Basic',
                       'XDG_RUNTIME_DIR':str(tmp/'runtime'),'PATH':str(tmp/'bin')+os.pathsep+os.environ['PATH']}
    if platform == 'wayland':
        env['XDG_RUNTIME_DIR'] = os.environ['XDG_RUNTIME_DIR']
        env.pop('QT_QUICK_BACKEND', None)
    r=subprocess.run(['quickshell','--no-color','-p',str(tmp/'shell.qml')],env=env,capture_output=True,text=True,timeout=20)
    log=r.stdout+r.stderr
    print(log)
    assert r.returncode==0 and 'PASS:' in log and not any(s in log for s in ('ReferenceError','TypeError','Unable to assign','Failed to load')),log
    exports=list((tmp/'pictures/Theme Favorites').glob('*.png'))
    assert len(exports)>=2
    assert all(p.stat().st_size > 0 for p in exports), 'Cancelled export left an empty image'
    data=min((p for p in exports if p.stat().st_size > 0), key=lambda p: p.stat().st_mtime_ns).read_bytes()
    assert exports[0].stat().st_mode & 0o777 == 0o600
    assert data[:8]==b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II',data[16:24])==(1800,1200)
    (artifacts/'share.png').write_bytes(data)
    print('PASS: 1800x1200 PNG saved privately to isolated Pictures directory')
