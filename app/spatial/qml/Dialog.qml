// A dialog: a dim backdrop (never blurred) and a depth-4 surface with radius 28 and a dense
// fill, so no blurred layer is added while it is open. Title, body, and buttons on the right
// (the default slot). Escape closes it; it scales in from 0.96 with the ease-out curve.
import QtQuick

Item {
    id: dlg
    property string title: ""
    property string body: ""
    property real panelWidth: 480
    property bool open: false
    default property alias buttons: btns.data
    signal closed()
    anchors.fill: parent
    visible: open || fade.running
    z: 100
    function show() { open = true; card.forceActiveFocus() }
    function hide() { open = false; closed() }

    Rectangle {
        anchors.fill: parent
        color: Theme.dim
        opacity: dlg.open ? 1 : 0
        Behavior on opacity { NumberAnimation { id: fade; duration: Theme.dur2 } }
        TapHandler { onTapped: dlg.hide() }
    }
    Surface {
        id: card
        depth: 4
        blur: false
        radius: Theme.rPanel
        padding: Theme.sp6
        width: Math.min(dlg.panelWidth, dlg.width - 2 * Theme.sp6)
        height: col.implicitHeight + 2 * padding
        anchors.centerIn: parent
        opacity: dlg.open ? 1 : 0
        scale: dlg.open ? 1 : 0.96
        Behavior on opacity { NumberAnimation { duration: Theme.dur2 } }
        Behavior on scale { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
        activeFocusOnTab: false
        Accessible.role: Accessible.Dialog
        Accessible.name: dlg.title
        Keys.onEscapePressed: dlg.hide()
        Column {
            id: col
            width: parent.width
            spacing: Theme.sp3
            Txt { width: parent.width; text: dlg.title; kind: "xl" }
            Txt { width: parent.width; text: dlg.body; tone: "secondary" }
            Item { width: 1; height: Theme.sp2 }
            Row { id: btns; anchors.right: parent.right; spacing: Theme.sp2; layoutDirection: Qt.RightToLeft }
        }
    }
}
