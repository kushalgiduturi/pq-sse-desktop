// A choice item: selected or not. Selected shows a check icon, a soft fill and bold text,
// so the state never depends on color alone.
import QtQuick

Rectangle {
    id: pick
    property string text: ""
    property bool selected: false
    signal clicked()

    implicitHeight: Math.max(Theme.touch ? 44 : 34, row.implicitHeight + 12)
    implicitWidth: row.implicitWidth + 28
    radius: height / 2
    color: selected ? Theme.press : (hover.hovered ? Theme.hover : "transparent")
    border.width: 1
    border.color: selected ? Theme.hairStrong : Theme.hair
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checked: selected
    Keys.onSpacePressed: clicked()
    Keys.onReturnPressed: clicked()
    Behavior on color { ColorAnimation { duration: Theme.dur1 } }
    Rectangle {
        visible: pick.activeFocus
        anchors.fill: parent; anchors.margins: -3
        radius: height / 2
        color: "transparent"; border.width: 2; border.color: Theme.ring
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Icon { visible: pick.selected; name: "check"; size: 14; color: Theme.text; anchors.verticalCenter: parent.verticalCenter }
        Txt { text: pick.text; kind: "sm"; strong: pick.selected; tone: pick.selected ? "primary" : "secondary"
              wrapMode: Text.NoWrap; lineHeight: 1.2; anchors.verticalCenter: parent.verticalCenter }
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: pick.clicked() }
}
