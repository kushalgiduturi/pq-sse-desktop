// Older name for small inline items. With a mark it is a status pill (ok, fail, or a dot for
// a neutral state). Without a mark it is plain text; a clickable one is a quiet text button
// (glossary terms, Story bar links). Pills only carry status.
import QtQuick

Item {
    id: chip
    property string text: ""
    property color dot: "transparent"
    property string mark: ""              // "", "dot", "ok", "fail"
    property bool clickable: false
    property real maxWidth: 100000
    signal clicked()

    readonly property bool status: mark !== ""
    readonly property string pillStatus: mark === "ok" ? "ok" : mark === "fail" ? "bad" : "neutral"
    implicitHeight: status ? pill.implicitHeight : Math.max(28, label.implicitHeight + 8)
    implicitWidth: status ? pill.implicitWidth : label.implicitWidth + (clickable ? 20 : 0)
    width: Math.min(implicitWidth, maxWidth)
    height: implicitHeight
    activeFocusOnTab: clickable
    Accessible.role: clickable ? Accessible.Button : Accessible.StaticText
    Accessible.name: (mark === "ok" ? T.ok + ": " : mark === "fail" ? T.failed + ": " : "") + chip.text
    Keys.onReturnPressed: if (clickable) clicked()
    Keys.onSpacePressed: if (clickable) clicked()

    Pill { id: pill; visible: chip.status; text: chip.text; status: chip.pillStatus; width: Math.min(implicitWidth, chip.maxWidth) }
    Rectangle {
        visible: !chip.status && chip.clickable
        anchors.fill: parent
        radius: height / 2
        color: hover.hovered ? Theme.hover : "transparent"
        border.width: chip.activeFocus ? 2 : 0
        border.color: Theme.ring
    }
    Txt {
        id: label
        visible: !chip.status
        anchors.centerIn: parent
        width: Math.min(implicitWidth, chip.maxWidth - (chip.clickable ? 20 : 0))
        text: chip.text
        kind: "sm"
        tone: chip.clickable ? "primary" : "secondary"
        strong: chip.clickable
        wrapMode: Text.NoWrap
        elide: Text.ElideRight
        lineHeight: 1.2
    }
    HoverHandler { id: hover; enabled: chip.clickable; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: chip.clickable; onTapped: chip.clicked() }
}
