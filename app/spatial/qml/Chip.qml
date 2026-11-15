// A small status pill: an optional mark (dot, check or cross shape) plus a word.
// The word carries the meaning; the color only supports it.
import QtQuick

Rectangle {
    id: chip
    property string text: ""
    property color dot: "transparent"
    property string mark: ""              // "", "dot", "ok", "fail"
    property bool clickable: false
    signal clicked()

    implicitHeight: Math.max(30, label.implicitHeight + 12)
    property real maxWidth: 100000
    implicitWidth: row.implicitWidth + 24
    width: Math.min(implicitWidth, maxWidth)
    radius: height / 2
    color: Theme.tint(Theme.glassRaised, 0.9)
    border.width: chip.activeFocus ? 2 : 1
    border.color: chip.activeFocus ? Theme.textPrimary : Theme.tint(Theme.glassStroke, 0.6)
    activeFocusOnTab: clickable
    Accessible.role: clickable ? Accessible.Button : Accessible.StaticText
    Accessible.name: (mark === "ok" ? T.ok + ": " : mark === "fail" ? T.failed + ": " : "") + chip.text
    Keys.onReturnPressed: if (clickable) clicked()
    Keys.onSpacePressed: if (clickable) clicked()

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Item {
            visible: chip.mark !== ""
            width: 12; height: 12
            anchors.verticalCenter: parent.verticalCenter
            Rectangle { visible: chip.mark === "dot"; anchors.fill: parent; radius: 6; color: chip.dot }
            Text {
                visible: chip.mark === "ok" || chip.mark === "fail"
                anchors.centerIn: parent
                text: chip.mark === "ok" ? "✓" : "✕"
                color: chip.mark === "ok" ? Theme.ok : Theme.fail
                font.pixelSize: Theme.body; font.weight: Font.Bold
            }
        }
        Text {
            id: label
            text: chip.text
            width: Math.min(implicitWidth, chip.maxWidth - 24 - (chip.mark !== "" ? 20 : 0))
            elide: Text.ElideRight
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
        }
    }
    HoverHandler { enabled: chip.clickable; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: chip.clickable; onTapped: chip.clicked() }
}
