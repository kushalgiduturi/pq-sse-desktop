// Segmented control with a sliding thumb. Arrow keys move the selection.
import QtQuick

Item {
    id: seg
    property var labels: []
    property int current: 0
    property string name: ""
    signal chosen(int index)

    readonly property real cell: width / Math.max(1, labels.length)
    implicitHeight: Theme.controlHeight
    implicitWidth: 400
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    Accessible.name: seg.name
    Keys.onLeftPressed: if (current > 0) chosen(current - 1)
    Keys.onRightPressed: if (current < labels.length - 1) chosen(current + 1)

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.tint(Theme.glassRaised, 0.9)
        border.width: seg.activeFocus ? 2 : 1
        border.color: seg.activeFocus ? Theme.textPrimary : Theme.tint(Theme.glassStroke, 0.6)
    }
    Rectangle {
        x: seg.current * seg.cell + 4
        y: 4
        width: seg.cell - 8
        height: parent.height - 8
        radius: height / 2
        color: Theme.accent
        Behavior on x { NumberAnimation { duration: Theme.moveBase; easing.type: Easing.OutCubic } }
    }
    Repeater {
        model: seg.labels
        Item {
            id: cellItem
            required property string modelData
            required property int index
            x: index * seg.cell
            width: seg.cell
            height: seg.height
            Accessible.role: Accessible.PageTab
            Accessible.name: modelData
            Text {
                anchors.centerIn: parent
                width: parent.width - 12
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                text: cellItem.modelData
                color: cellItem.index === seg.current ? Theme.accentOn : Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.body * 0.95
                font.weight: cellItem.index === seg.current ? Font.DemiBold : Font.Normal
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: seg.chosen(cellItem.index) }
        }
    }
}
