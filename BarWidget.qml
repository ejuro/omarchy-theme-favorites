import QtQuick
import qs.Ui

BarWidget {
    id: root
    moduleName: "io.github.ejuro.theme-favorites"
    readonly property bool opened: panel.item ? panel.item.opened : false
    readonly property bool popoutSwitchClosing: panel.item ? panel.item.popoutSwitchClosing : false
    function open() { if (panel.item) panel.item.open() }
    function close() { if (panel.item) panel.item.close() }
    function toggle() { if (opened) close(); else open() }
    function closeForPopoutSwitch() { if (panel.item) panel.item.closeForPopoutSwitch() }
    function inject() {
        if (!panel.item) return
        panel.item.bar = root.bar
        panel.item.anchorItem = button
        panel.item.hostWidget = root
    }
    onBarChanged: inject()
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Loader {
        id: panel
        source: Qt.resolvedUrl("FavoritesPanel.qml")
        visible: false
        onLoaded: { root.inject(); Qt.callLater(root.inject) }
    }
    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: "󰏘"
        active: root.opened
        tooltipText: "Theme Favorites"
        onPressed: root.toggle()
    }
}
