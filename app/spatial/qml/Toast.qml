// A toast: a small depth-4 surface above the dock, with a status icon, one sentence and an
// optional action. Dense fill (it can appear over the dock, and glass is never nested).
// It rises 8 px and fades in, and leaves after a few seconds.
import QtQuick

Surface {
    id: toast
    property string text: ""
    property string status: "ok"
    property string action: ""
    property int timeout: 5000
    signal actionClicked()
    function show(message, kind) { text = message; status = kind || "ok"; shown = true; timer.restart() }
    property bool shown: false
    depth: 4
    blur: false
    radius: Theme.rFloat
    padding: 0
    width: Math.min(row.implicitWidth + 2 * Theme.sp4, 560)
    height: Math.max(Theme.ctlH + Theme.sp3, row.implicitHeight + 2 * Theme.sp3)
    opacity: shown ? 1 : 0
    visible: opacity > 0
    transform: Translate { y: toast.shown ? 0 : 8; Behavior on y { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } } }
    Behavior on opacity { NumberAnimation { duration: Theme.dur2 } }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: toast.text
    Timer { id: timer; interval: toast.timeout; onTriggered: toast.shown = false }

    Row {
        id: row
        x: Theme.sp4
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.sp3
        Icon {
            name: toast.status === "bad" ? "alert" : toast.status === "warn" ? "alert" : "check"
            color: toast.status === "bad" ? Theme.bad : toast.status === "warn" ? Theme.warn : Theme.ok
            size: 18
            anchors.verticalCenter: parent.verticalCenter
        }
        Txt { text: toast.text; wrapMode: Text.NoWrap; lineHeight: 1.0; anchors.verticalCenter: parent.verticalCenter }
        Button { visible: toast.action.length > 0; kind: "quiet"; small: true; text: toast.action
                 anchors.verticalCenter: parent.verticalCenter; onClicked: toast.actionClicked() }
    }
}
