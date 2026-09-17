import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import qs.Commons
import qs.Ui

Column {
    id: root
    property var snapshot: ({periods: {}, status: "starting"})
    property string trackingError: ""
    property bool exportMode: false
    signal shareRequested()
    readonly property bool previewsReady: {
        var items = themesList.contentItem.children
        for (var i = 0; i < items.length; i++)
            if (items[i].previewLoading === true) return false
        return true
    }
    property int selectedPeriod: 0
    property int selectedRow: -1
    readonly property var periodKeys: ["week", "month", "year", "all"]
    readonly property var periodLabels: ["This week", "This month", "This year", "All time"]
    readonly property var rankedRows: snapshot.periods ? (snapshot.periods[periodKeys[selectedPeriod]] || []) : []
    readonly property var rows: rankedRows.slice(0, exportMode ? 5 : 20)
    onRowsChanged: selectedRow = Math.min(selectedRow, rows.length - 1)
    readonly property color ink: Color.popups.text
    property real availableHeight: 0
    readonly property real rowHeight: Style.space(61)
    readonly property real desiredListHeight: rows.length ? Math.min(5, rows.length) * rowHeight : Style.space(132)
    readonly property real chromeHeight: header.implicitHeight + Style.space(35) + footer.implicitHeight + spacing * 3
    readonly property real preferredHeight: chromeHeight + desiredListHeight
    readonly property real scrollPosition: themesList.contentY
    readonly property real listHeight: listViewport.height
    readonly property real footerY: footer.y
    spacing: Style.space(10)
    onSelectedPeriodChanged: {
        selectedRow = -1
        themesList.positionViewAtBeginning()
    }

    function changePeriod(delta) { selectedPeriod = (selectedPeriod + delta + 4) % 4 }
    function changeRow(delta) {
        if (!rows.length) return
        selectedRow = Math.max(0, Math.min(rows.length - 1, selectedRow + delta))
        themesList.positionViewAtIndex(selectedRow, ListView.Contain)
    }
    function openSelectedRepository() {
        if (selectedRow >= 0 && rows[selectedRow] && rows[selectedRow].url)
            Qt.openUrlExternally(rows[selectedRow].url)
    }
    function duration(seconds) {
        if (seconds < 60) return "<1m"
        var minutes = Math.floor(seconds / 60)
        if (minutes < 60) return minutes + "m"
        var hours = Math.floor(minutes / 60)
        if (hours < 24) return hours + "h" + (minutes % 60 ? " " + (minutes % 60) + "m" : "")
        var days = Math.floor(hours / 24)
        if (days < 365) return days + "d" + (hours % 24 ? " " + (hours % 24) + "h" : "")
        var years = Math.floor(days / 365)
        return years + "y" + (days % 365 ? " " + (days % 365) + "d" : "")
    }

    Column {
        id: header
        width: parent.width
        spacing: Style.space(4)
        Item {
            width: parent.width
            height: Style.space(26)
            Text {
                anchors { left: parent.left; right: shareButton.left; verticalCenter: parent.verticalCenter }
                text: "Theme Favorites"
                textFormat: Text.PlainText
                color: root.ink
                font.family: Style.font.family
                font.pixelSize: Style.font.heading
                font.bold: true
            }
            PanelActionButton {
                id: shareButton
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                visible: !root.exportMode
                enabled: root.rows.length > 0
                iconText: "󰒪"
                tooltipText: "Export your top five themes"
                foreground: root.ink
                onClicked: root.shareRequested()
                Accessible.role: Accessible.Button
                Accessible.name: "Export your top five themes"
                Accessible.onPressAction: if (enabled) root.shareRequested()
            }
        }
        Text {
            width: parent.width
            text: root.exportMode ? "My most-used themes, ranked by time." : "Your 20 most-used themes, ranked by time."
            wrapMode: Text.WordWrap
            color: root.ink
            opacity: 0.45
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
        }
    }

    Row {
        width: parent.width
        height: Style.space(35)
        Repeater {
            model: root.periodLabels
            delegate: Rectangle {
                id: tab
                required property int index
                required property string modelData
                width: root.width / 4
                height: parent.height
                color: Util.alpha(Color.accent, root.selectedPeriod === index ? 0.1 : tabMouse.containsMouse ? 0.05 : 0)
                Text {
                    anchors.centerIn: parent
                    text: tab.modelData
                    color: root.selectedPeriod === tab.index ? Color.accent : root.ink
                    opacity: root.selectedPeriod === tab.index ? 1 : 0.65
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    font.bold: root.selectedPeriod === tab.index
                }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: root.selectedPeriod === tab.index ? Style.space(2) : 1
                    color: root.selectedPeriod === tab.index ? Color.accent : Util.alpha(root.ink, 0.12)
                }
                MouseArea {
                    id: tabMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.selectedPeriod = tab.index
                }
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData
                Accessible.selected: root.selectedPeriod === index
                Accessible.onPressAction: root.selectedPeriod = index
            }
        }
    }

    Item {
        id: listViewport
        width: parent.width
        height: root.availableHeight > 0
            ? Math.max(0, Math.min(root.desiredListHeight, root.availableHeight - root.chromeHeight))
            : root.desiredListHeight
        ListView {
            id: themesList
            anchors.fill: parent
            // Keep delegates and scroll position stable as usage times refresh.
            model: root.rows.length
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height
            reuseItems: true
            Controls.ScrollBar.vertical: Controls.ScrollBar {
                id: scrollBar
                policy: themesList.contentHeight > themesList.height ? Controls.ScrollBar.AlwaysOn : Controls.ScrollBar.AlwaysOff
                width: Style.space(4)
                minimumSize: 0.08
                contentItem: Rectangle {
                    implicitWidth: Style.space(4)
                    radius: width / 2
                    color: Util.alpha(root.ink, scrollBar.pressed ? 0.55 : 0.23)
                }
                background: Item {}
            }
            delegate: Rectangle {
                id: themeRow
                required property int index
                readonly property var modelData: root.rows[index]
                readonly property bool previewLoading: preview.status === Image.Loading
                width: themesList.width - (themesList.contentHeight > themesList.height ? Style.space(10) : 0)
                height: root.rowHeight
                color: Util.alpha(root.ink, hover.hovered || root.selectedRow === index ? 0.04 : 0)
                HoverHandler { id: hover }
                PanelToolTip {
                    visible: hover.hovered && !repoMouse.containsMouse && !themesList.moving
                    text: themeRow.modelData.name + "\n" + themeRow.modelData.credit
                        + (themeRow.modelData.palette_credit ? "\n" + themeRow.modelData.palette_credit : "")
                        + "\nTime used: " + Math.floor(themeRow.modelData.seconds / 3600) + "h "
                        + (Math.floor(themeRow.modelData.seconds / 60) % 60) + "m"
                        + "\nSelected "
                        + themeRow.modelData.selections + (themeRow.modelData.selections === 1 ? " time" : " times")
                        + " · " + root.periodLabels[root.selectedPeriod].toLowerCase()
                }
                RowLayout {
                    anchors { fill: parent; leftMargin: Style.space(4); rightMargin: Style.space(4) }
                    spacing: Style.space(10)
                    Text {
                        text: themeRow.index + 1
                        color: themeRow.index === 0 ? Color.accent : root.ink
                        opacity: themeRow.index === 0 ? 1 : 0.4
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        Layout.preferredWidth: Style.space(root.rows.length > 99 ? 27 : root.rows.length > 9 ? 20 : 13)
                    }
                    Rectangle {
                        Layout.preferredWidth: Style.space(52)
                        Layout.preferredHeight: Style.space(36)
                        color: themeRow.modelData.palette.length ? themeRow.modelData.palette[0] : Color.background
                        clip: true
                        Image {
                            id: preview
                            anchors.fill: parent
                            source: themeRow.modelData.preview
                            sourceSize: root.exportMode ? Qt.size(234, 162) : Qt.size(156, 108)
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            visible: status === Image.Ready
                        }
                        Row {
                            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                            height: preview.status === Image.Ready ? Style.space(4) : parent.height
                            Repeater {
                                model: themeRow.modelData.palette
                                Rectangle {
                                    required property string modelData
                                    width: Style.space(52) / themeRow.modelData.palette.length
                                    height: parent.height
                                    color: modelData
                                }
                            }
                        }
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: Style.space(4)
                        Text {
                            width: parent.width
                            text: themeRow.modelData.name
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: root.ink
                            font.family: Style.font.family
                            font.pixelSize: Style.font.body
                            font.bold: themeRow.index === 0
                        }
                        Text {
                            width: parent.width
                            text: themeRow.modelData.credit
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                            color: root.ink
                            opacity: 0.5
                            font.family: Style.font.family
                            font.pixelSize: Style.font.bodySmall
                        }
                    }
                    Text {
                        text: root.duration(themeRow.modelData.seconds)
                        color: themeRow.index === 0 ? Color.accent : root.ink
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        horizontalAlignment: Text.AlignRight
                        Layout.minimumWidth: Style.space(54)
                    }
                    Item {
                        Layout.preferredWidth: Style.space(24)
                        Layout.preferredHeight: Style.space(32)
                        Text {
                            anchors.centerIn: parent
                            text: ""
                            color: repoMouse.containsMouse ? Color.accent : root.ink
                            opacity: themeRow.modelData.url ? 0.8 : 0.2
                            font.family: Style.font.family
                            font.pixelSize: Style.space(17)
                        }
                        MouseArea {
                            id: repoMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: themeRow.modelData.url ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: if (themeRow.modelData.url) Qt.openUrlExternally(themeRow.modelData.url)
                        }
                        PanelToolTip {
                            visible: repoMouse.containsMouse
                            text: themeRow.modelData.url ? "Visit on GitHub · give this theme a star" : "No GitHub repository listed"
                        }
                        Accessible.role: Accessible.Link
                        Accessible.name: "Open " + themeRow.modelData.name + " on GitHub"
                        Accessible.onPressAction: if (themeRow.modelData.url) Qt.openUrlExternally(themeRow.modelData.url)
                    }
                }
                Rectangle {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: 1
                    color: Util.alpha(root.ink, 0.07)
                    visible: themeRow.index < root.rows.length - 1
                }
            }
        }
        Item {
            anchors.fill: parent
            visible: root.rows.length === 0
            Column {
                anchors.centerIn: parent
                spacing: Style.space(8)
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: root.snapshot.status === "starting" ? "Starting your history…" : "Your favorites will find their place."
                    color: root.ink
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Use a theme to start building this list."
                    color: root.ink
                    opacity: 0.5
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                }
            }
        }
    }

    Column {
        id: footer
        width: parent.width
        spacing: Style.space(4)
        topPadding: Style.space(6)
        Text {
            width: parent.width
            height: Style.space(20)
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            text: root.snapshot.since ? "Tracking themes since " + root.snapshot.since : "Starting tracking…"
            color: root.ink
            opacity: 0.5
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
        }
        Text {
            id: trackingLabel
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            text: root.trackingError ? "Retrying…" : root.snapshot.status === "tracking" ? ""
                : root.snapshot.status === "paused" ? "Paused" : root.snapshot.status === "unavailable" ? "Waiting for desktop" : ""
            visible: text.length > 0
            color: root.ink
            opacity: 0.4
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            HoverHandler { id: statusHover }
            PanelToolTip {
                visible: statusHover.hovered
                text: root.trackingError || "Ranked by unlocked desktop time.\nLocked, suspended and display-off time is excluded."
            }
        }
    }
}
