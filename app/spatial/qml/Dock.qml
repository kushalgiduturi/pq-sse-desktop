// The floating dock: five destinations with icon and label, keys 1 to 5.
// The hovered item grows; its neighbours grow a little.
import QtQuick

Glass {
    id: dock
    property string current: "journey"
    property int hovered: -1
    signal chosen(string key)

    floating: true
    radius: Theme.rDock
    padding: 10
    width: row.implicitWidth + 36
    height: 78 * Math.max(1, Theme.scale)
    Accessible.role: Accessible.ToolBar
    Accessible.name: "Destinations"

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 6
        Repeater {
            model: DEST
            Item {
                id: cell
                required property var modelData
                required property int index
                readonly property bool active: dock.current === modelData.key
                readonly property int distance: dock.hovered < 0 ? 9 : Math.abs(dock.hovered - index)
                width: 98 * Math.max(1, Theme.scale)
                height: 58 * Math.max(1, Theme.scale)
                scale: distance === 0 ? 1.16 : distance === 1 ? 1.05 : 1.0
                transformOrigin: Item.Bottom
                activeFocusOnTab: true
                Behavior on scale { enabled: !Theme.reduceMotion; SpringAnimation { spring: Theme.hoverSpring; damping: Theme.hoverDamping } }
                Accessible.role: Accessible.Button
                Accessible.name: modelData.label + ". " + modelData.hint + ". Key " + (index + 1)
                Accessible.onPressAction: dock.chosen(modelData.key)
                Keys.onReturnPressed: dock.chosen(modelData.key)
                Keys.onSpacePressed: dock.chosen(modelData.key)

                Rectangle {
                    anchors.fill: parent
                    radius: 16
                    color: cell.active ? Theme.accent : (cell.distance === 0 ? Theme.tint(Theme.glassRaised, 0.9) : "transparent")
                    border.width: cell.activeFocus ? 2 : 0
                    border.color: Theme.textPrimary
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                Icon {
                    name: cell.modelData.key
                    color: cell.active ? Theme.accentOn : Theme.textPrimary
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 7
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 6
                    text: cell.modelData.label
                    color: cell.active ? Theme.accentOn : Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.caption
                    font.weight: cell.active ? Font.DemiBold : Font.Normal
                }
                Text {
                    anchors.right: parent.right; anchors.top: parent.top
                    anchors.rightMargin: 8; anchors.topMargin: 4
                    text: cell.index + 1
                    color: cell.active ? Theme.accentOn : Theme.textMuted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.caption * 0.85
                }
                HoverHandler {
                    cursorShape: Qt.PointingHandCursor
                    onHoveredChanged: dock.hovered = hovered ? cell.index : (dock.hovered === cell.index ? -1 : dock.hovered)
                }
                TapHandler { onTapped: dock.chosen(cell.modelData.key) }
            }
        }
    }
}
