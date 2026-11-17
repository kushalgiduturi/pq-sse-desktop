// The dock: a small depth-4 tray at the bottom center. Each item is a line icon over a short
// label; the selected one carries a dot under it. Hover magnifies the item under the pointer
// and its neighbours a little, a press dips with the press spring, and the tray tilts at
// most 3 degrees toward the pointer (navigation only; none with Reduce motion or touch).
// items: [{key, icon, label}]
import QtQuick

Surface {
    id: dock
    property var items: []
    property string current: ""
    property bool labelsOnly: false
    signal chosen(string key)
    depth: 4
    radius: Q.rFloat
    padding: Q.sp2
    width: row.implicitWidth + 2 * padding
    height: row.implicitHeight + 2 * padding
    Accessible.role: Accessible.PageTabList

    property real px: -1
    transform: Rotation {
        origin.x: dock.width / 2; origin.y: dock.height / 2
        axis { x: 0; y: 1; z: 0 }
        angle: dock.px < 0 ? 0 : ((dock.px / dock.width) - 0.5) * 2 * Q.tiltMax
        Behavior on angle { NumberAnimation { duration: Q.dur3; easing.type: Easing.OutCubic } }
    }
    HoverHandler {
        id: dh
        onPointChanged: dock.px = hovered ? point.position.x : -1
        onHoveredChanged: if (!hovered) dock.px = -1
    }

    Row {
        id: row
        spacing: Q.sp1
        Repeater {
            model: dock.items
            Item {
                id: it
                required property var modelData
                required property int index
                readonly property bool sel: modelData.key === dock.current
                readonly property real cx: x + width / 2 + dock.padding
                readonly property real near: dock.px < 0 || Q.still ? 0 : Math.max(0, 1 - Math.abs(dock.px - cx) / 120)
                width: Math.max(72, lab.implicitWidth + 24)
                height: dock.labelsOnly ? lab.implicitHeight + 28 : 62
                activeFocusOnTab: true
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Accessible.selected: sel
                Keys.onReturnPressed: dock.chosen(modelData.key)
                Keys.onSpacePressed: dock.chosen(modelData.key)
                scale: tap.pressed ? 0.94 : 1 + 0.08 * near
                Behavior on scale { enabled: !Q.reduceMotion; NumberAnimation { duration: Q.dur2; easing.type: Easing.OutBack; easing.overshoot: Q.pressOvershoot } }

                Rectangle {
                    anchors.fill: parent
                    radius: Q.rCard
                    color: it.sel ? Q.hover : (ih.hovered ? Q.rowHover : "transparent")
                }
                Rectangle {
                    visible: it.activeFocus
                    anchors.fill: parent; anchors.margins: -2
                    radius: Q.rCard + 2
                    color: "transparent"; border.width: 2; border.color: Q.ring
                }
                Column {
                    anchors.centerIn: parent
                    anchors.verticalCenterOffset: -3
                    spacing: 4
                    Icon { visible: !dock.labelsOnly; name: it.modelData.icon; size: 22; color: it.sel ? Q.text : Q.text2; anchors.horizontalCenter: parent.horizontalCenter }
                    Txt { id: lab; text: it.modelData.label; kind: "xs"; strong: it.sel; tone: it.sel ? "primary" : "secondary"
                          wrapMode: Text.NoWrap; lineHeight: 1.0; anchors.horizontalCenter: parent.horizontalCenter }
                }
                Rectangle {          // the selected dot
                    visible: it.sel
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom; anchors.bottomMargin: 4
                    width: 4; height: 4; radius: 2
                    color: Q.text
                }
                HoverHandler { id: ih; cursorShape: Qt.PointingHandCursor }
                TapHandler { id: tap; onTapped: dock.chosen(it.modelData.key) }
            }
        }
    }
}
