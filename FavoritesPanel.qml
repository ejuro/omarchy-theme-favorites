import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "io.github.ejuro.theme-favorites"
    manageIpc: false
    property var anchorItem: null
    property var hostWidget: null
    property var snapshot: ({periods: {}, status: "starting"})
    property double now: Date.now() / 1000
    property string loadError: ""
    readonly property bool stale: !snapshot.updated_at || now - snapshot.updated_at > 20
    function open() {
        sharePanel.dismiss()
        root.controller.show()
        reportFile.reload()
        if (!refreshProcess.running) refreshProcess.running = true
    }
    onOpenedChanged: if (!opened) sharePanel.dismiss()
    FileView {
        id: reportFile
        path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state")
            + "/theme-favorites/snapshot.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { root.snapshot = JSON.parse(text()); root.loadError = "" }
            catch (error) { root.loadError = "Could not read theme history." }
        }
    }
    Process { id: refreshProcess; command: ["omarchy-shell", "theme-favorites", "refresh"] }
    Timer {
        interval: 5000; running: true; repeat: true
        onTriggered: { root.now = Date.now() / 1000; if (root.stale) reportFile.reload() }
    }
    KeyboardPanel {
        id: panel
        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: keyCatcher
        contentWidth: panel.fittedContentWidth(Style.space(440))
        contentHeight: panel.fittedContentHeight(sharePanel.opened ? sharePanel.preferredHeight : content.preferredHeight)
        PanelKeyCatcher {
            id: keyCatcher
            anchors.fill: parent
            onCloseRequested: sharePanel.opened ? sharePanel.dismiss() : root.close()
            onMoveRequested: function(dx, dy) {
                if (sharePanel.opened) return
                if (dx) content.changePeriod(dx)
                if (dy) content.changeRow(dy)
            }
            onActivateRequested: sharePanel.opened ? sharePanel.save() : content.openSelectedRepository()
            onTabRequested: function(direction) { if (!sharePanel.opened) content.changePeriod(direction) }
            SharePanel { id: sharePanel; anchors.fill: parent }
            FavoritesContent {
                id: content
                anchors.fill: parent
                visible: !sharePanel.opened
                availableHeight: height
                snapshot: root.snapshot
                onShareRequested: {
                    sharePanel.show(root.snapshot, selectedPeriod)
                }
                trackingError: root.loadError || (root.stale ? "Waiting for the tracking service." : "")
            }
        }
    }
}
