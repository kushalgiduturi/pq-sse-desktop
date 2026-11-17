// A flat row: the panel is the surface. A hairline under it, a 4 percent tint on hover,
// a stronger tint when selected. Content goes in the default slot.
import QtQuick

Item {
    id: r
    property bool selected: false
    property bool hairline: true
    property bool clickable: false
    property real padY: Q.sp3
    default property alias content: inner.data
    signal clicked()
    implicitHeight: inner.childrenRect.height + 2 * padY
    activeFocusOnTab: clickable
    Accessible.role: clickable ? Accessible.Button : Accessible.ListItem
    Keys.onReturnPressed: if (clickable) clicked()
    Keys.onSpacePressed: if (clickable) clicked()

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: -Q.sp3; anchors.rightMargin: -Q.sp3
        radius: Q.rSm
        color: r.selected ? Q.press : (hover.hovered && r.clickable ? Q.rowHover : "transparent")
        Behavior on color { ColorAnimation { duration: Q.dur1 } }
    }
    Rectangle {
        visible: r.activeFocus
        anchors.fill: parent
        anchors.leftMargin: -Q.sp3; anchors.rightMargin: -Q.sp3
        radius: Q.rSm
        color: "transparent"; border.width: 2; border.color: Q.ring
    }
    Item { id: inner; x: 0; y: r.padY; width: r.width; height: childrenRect.height }
    Rectangle { visible: r.hairline; anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Q.hair }
    HoverHandler { id: hover; enabled: r.clickable; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: r.clickable; onTapped: { r.forceActiveFocus(); r.clicked() } }
}
