import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

Item {
    id: root
    property bool opened: false
    visible: opened
    readonly property real preferredHeight: width * 2 / 3 + Style.space(120)
    property int generation: 0
    property string pendingPath: ""
    function discard(path) {
        if (path) Quickshell.execDetached(["python3", helper, "discard-empty", path])
    }
    function dismiss() {
        generation++
        discard(pendingPath)
        pendingPath = ""
        busy = false
        deadline.stop()
        opened = false
    }
    property var snapshot: ({periods: {}})
    property int selectedPeriod: 0
    property bool busy: false
    property string savedPath: ""
    property string message: "Export an image to upload wherever you like."
    readonly property string helper: decodeURIComponent(Qt.resolvedUrl("share.py").toString().replace(/^file:\/\//, ""))
    function show(data, period) {
        dismiss()
        snapshot = JSON.parse(JSON.stringify(data))
        selectedPeriod = period
        card.refreshWallpaper()
        savedPath = ""
        message = "Export an image to upload wherever you like."
        opened = true
    }
    function save() {
        if (!opened || busy || prepare.running || !card.ready) return
        busy = true
        message = "Creating image…"
        prepare.requestGeneration = generation
        deadline.restart()
        prepare.running = true
    }
    function capture(path) {
        pendingPath = path
        var request = generation
        var accepted = card.grabToImage(function(result) {
            if (request !== root.generation) { root.discard(path); return }
            pendingPath = ""
            deadline.stop()
            if (!result.saveToFile(path)) { root.discard(path); busy = false; message = "Could not save the image. Try again."; return }
            savedPath = path
            busy = false
            message = "Saved to " + path
        }, Qt.size(Math.round(1800 / card.QsWindow.window.devicePixelRatio), Math.round(1200 / card.QsWindow.window.devicePixelRatio)))
        if (!accepted) { discard(path); pendingPath = ""; deadline.stop(); busy = false; message = "Could not create the image. Keep the preview open and try again." }
    }
    Process {
        id: prepare
        property int requestGeneration: -1
        command: ["python3", root.helper, "prepare"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    var reply = JSON.parse(text)
                    if (prepare.requestGeneration !== root.generation || !root.busy) { root.discard(reply.path); return }
                    if (!reply.path) throw new Error("missing path")
                    root.capture(reply.path)
                } catch (e) { deadline.stop(); root.busy = false; root.message = "Could not create the image file." }
            }
        }
    }
    Timer {
        id: deadline
        interval: 10000
        onTriggered: {
            root.generation++
            root.discard(root.pendingPath)
            root.pendingPath = ""
            root.busy = false
            prepare.running = false
            root.message = "Export timed out. Please try again."
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 0
        spacing: Style.space(8)
        RowLayout {
            Layout.fillWidth: true
            Ui.Button {
                text: "Back"
                foreground: Color.popups.text
                onClicked: root.dismiss()
            }
            Text {
                Layout.fillWidth: true
                text: "Export preview"
                color: Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                horizontalAlignment: Text.AlignRight
            }
        }
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ShareCard {
                id: card
                x: (parent.width - width) / 2
                y: (parent.height - height) / 2
                scale: Math.min(parent.width / width, parent.height / height)
                snapshot: root.snapshot
                selectedPeriod: root.selectedPeriod
            }
        }
        Text {
            Layout.fillWidth: true
            text: root.message
            textFormat: Text.PlainText
            elide: Text.ElideMiddle
            maximumLineCount: 1
            color: Color.popups.text
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
        }
        RowLayout {
            Layout.fillWidth: true
            Ui.Button {
                text: "Show file"
                visible: root.savedPath !== ""
                foreground: Color.popups.text
                focusable: true
                onClicked: Qt.openUrlExternally("file://" + root.savedPath.substring(0, root.savedPath.lastIndexOf("/")).split("/").map(encodeURIComponent).join("/"))
            }
            Item { Layout.fillWidth: true }
            Ui.Button {
                text: "Export image"
                enabled: !root.busy && !prepare.running && card.ready
                foreground: Color.popups.text
                focusable: true
                onClicked: root.save()
            }

        }
    }
}
