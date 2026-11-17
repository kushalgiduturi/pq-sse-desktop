// Segmented control: a depth-1 inset track with a raised pill that slides with the spring.
// The selected label is bolder; arrow keys move the selection.
import QtQuick

Item {
    id: seg
    property var labels: []
    property int current: 0
    property string name: ""
    signal chosen(int index)

    readonly property real cell: width / Math.max(1, labels.length)
    implicitHeight: Theme.ctlH
    implicitWidth: 360
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    Accessible.name: seg.name
    Keys.onLeftPressed: if (current > 0) chosen(current - 1)
    Keys.onRightPressed: if (current < labels.length - 1) chosen(current + 1)

    Surface { anchors.fill: parent; depth: 1; radius: height / 2; padding: 0 }
    Item {
        id: pill
        x: seg.current * seg.cell + 3
        y: 3
        width: seg.cell - 6
        height: seg.height - 6
        Behavior on x {
            enabled: !Theme.reduceMotion
            NumberAnimation { duration: Theme.dur4; easing.type: Easing.OutBack; easing.overshoot: Theme.springOvershoot }
        }
        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: Theme.raised
            Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                        anchors.leftMargin: parent.radius * 0.6; anchors.rightMargin: parent.radius * 0.6
                        height: 1; color: Theme.edgeHi }
        }
        Rectangle {        // a short contact shadow so the pill reads as raised (light theme)
            z: -1
            anchors.fill: parent; anchors.topMargin: 1; anchors.bottomMargin: -1
            radius: height / 2
            color: Theme.raisedShade
        }
    }
    Rectangle {
        visible: seg.activeFocus
        anchors.fill: parent; anchors.margins: -3
        radius: height / 2
        color: "transparent"; border.width: 2; border.color: Theme.ring
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
            Accessible.selected: index === seg.current
            Txt {
                anchors.centerIn: parent
                width: parent.width - 12
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight; wrapMode: Text.NoWrap
                text: cellItem.modelData
                kind: "sm"
                strong: cellItem.index === seg.current
                tone: cellItem.index === seg.current ? "primary" : "secondary"
                lineHeight: 1.0
            }
            HoverHandler { cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: seg.chosen(cellItem.index) }
        }
    }
}
