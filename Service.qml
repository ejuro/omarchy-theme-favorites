import QtQuick
import Quickshell.Io

Item {
    id: root
    property var shell: null
    property var snapshot: ({since: "", periods: {}, status: "starting", current: ""})
    property string lastError: ""
    property bool stopping: false
    readonly property string script: decodeURIComponent(Qt.resolvedUrl("tracker.py").toString().replace(/^file:\/\//, ""))
    function refresh() { if (tracker.running) tracker.write("refresh\n") }

    Process {
        id: tracker
        command: ["python3", "-u", root.script, "watch"]
        stdinEnabled: true
        running: true
        stdout: SplitParser {
            onRead: function(line) {
                try { root.snapshot = JSON.parse(line); root.lastError = "" }
                catch (error) { root.lastError = "Could not read theme history." }
            }
        }
        stderr: StdioCollector {
            onStreamFinished: if (text.trim()) root.lastError = text.trim()
        }
        onExited: {
            if (!root.stopping) {
                root.lastError = root.lastError || "Tracking stopped. Retrying…"
                retry.restart()
            }
        }
    }
    Timer { id: retry; interval: 5000; onTriggered: tracker.running = true }
    IpcHandler {
        target: "theme-favorites"
        function status(): string { return JSON.stringify({snapshot: root.snapshot, error: root.lastError}) }
        function refresh(): void { root.refresh() }
    }
    Component.onDestruction: { stopping = true; tracker.running = false }
}
