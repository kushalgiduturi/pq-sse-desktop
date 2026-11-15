// A choice pill: selected or not. The selected state shows a check mark as well as a fill.
import QtQuick

Rectangle {
    id: pick
    property string text: ""
    property bool selected: false
    signal clicked()

    implicitHeight: Math.max(34, label.implicitHeight + 14)
    implicitWidth: label.implicitWidth + 28
    radius: height / 2
    color: selected ? Theme.tint(Theme.accent, 0.28) : Theme.tint(Theme.glassRaised, 0.9)
    border.width: selected || activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.textPrimary : selected ? Theme.accent : Theme.tint(Theme.glassStroke, 0.7)
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checked: selected
    Keys.onSpacePressed: clicked()
    Keys.onReturnPressed: clicked()
    Lbl {
        id: label
        anchors.centerIn: parent
        text: (pick.selected ? "✓ " : "") + pick.text
        size: Theme.body * 0.95
        strong: pick.selected
        wrapMode: Text.NoWrap
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: pick.clicked() }
}
