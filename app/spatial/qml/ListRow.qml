// A flat row: the panel is the surface. A hairline under it, a 4 percent tint on hover,
// a stronger tint when selected. Content goes in the default slot.
import QtQuick

Item {
    id: r
    property bool selected: false
    property bool hairline: true
    property bool clickable: false
    property real padY: Theme.sp3
    default property alias content: inner.data
    signal clicked()
    implicitHeight: inner.childrenRect.height + 2 * padY
    activeFocusOnTab: clickable
    Accessible.role: clickable ? Accessible.Button : Accessible.ListItem
    Keys.onReturnPressed: if (clickable) clicked()
    Keys.onSpacePressed: if (clickable) clicked()

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -Theme.sp3; anchors.rightMargin: -Theme.sp3
        radius: Theme.rSm
        color: r.selected ? Theme.press : (hover.hovered && r.clickable ? Theme.rowHover : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.dur1 } }
    }
    Rectangle {
        visible: r.activeFocus
        anchors.fill: parent
        anchors.leftMargin: -Theme.sp3; anchors.rightMargin: -Theme.sp3
        radius: Theme.rSm
        color: "transparent"; border.width: 2; border.color: Theme.ring
    }
    Item { id: inner; x: 0; y: r.padY; width: r.width; height: childrenRect.height }
    Rectangle { visible: r.hairline; anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
    HoverHandler { id: hover; enabled: r.clickable; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: r.clickable; onTapped: { r.forceActiveFocus(); r.clicked() } }
}
