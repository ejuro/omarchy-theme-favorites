import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

Rectangle {
    id: root
    width: 1200
    height: 800
    property var snapshot: ({periods: {}})
    property int selectedPeriod: 0
    property bool useWallpaper: true
    function refreshWallpaper() {
        wallpaper.source = ""
        Qt.callLater(function() {
            wallpaper.source = root.useWallpaper ? "file://" + Quickshell.env("HOME") + "/.local/state/omarchy/current/background" : ""
        })
    }
    Component.onCompleted: refreshWallpaper()
    onUseWallpaperChanged: refreshWallpaper()
    readonly property bool ready: wallpaper.status !== Image.Loading && favorites.previewsReady
    gradient: Gradient {
        GradientStop { position: 0; color: Qt.lighter(Color.background, 1.5) }
        GradientStop { position: 1; color: Color.background }
    }
    Image {
        id: wallpaper
        anchors.fill: parent
        cache: false
        sourceSize: Qt.size(1800, 1200)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
    }
    Rectangle { anchors.fill: parent; color: Util.alpha(Color.background, 0.16) }
    BorderSurface {
        anchors.centerIn: parent
        width: favorites.width + Style.space(32)
        height: favorites.implicitHeight + Style.space(32)
        scale: Math.min(1.3, 680 / height, 760 / width)
        color: Color.popups.background
        borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, 1)
        radius: Style.cornerRadius
        FavoritesContent {
            id: favorites
            x: Style.space(16); y: Style.space(16)
            width: Style.space(440)
            snapshot: root.snapshot
            selectedPeriod: root.selectedPeriod
            exportMode: true
            enabled: false
        }
    }
}
