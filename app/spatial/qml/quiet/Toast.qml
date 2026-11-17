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
    radius: Q.rFloat
    padding: 0
    width: Math.min(row.implicitWidth + 2 * Q.sp4, 560)
    height: Math.max(Q.ctlH + Q.sp3, row.implicitHeight + 2 * Q.sp3)
    opacity: shown ? 1 : 0
    visible: opacity > 0
    transform: Translate { y: toast.shown ? 0 : 8; Behavior on y { NumberAnimation { duration: Q.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Q.easeOutCurve } } }
    Behavior on opacity { NumberAnimation { duration: Q.dur2 } }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: toast.text
    Timer { id: timer; interval: toast.timeout; onTriggered: toast.shown = false }

    Row {
        id: row
        x: Q.sp4
        anchors.verticalCenter: parent.verticalCenter
        spacing: Q.sp3
        Icon {
            name: toast.status === "bad" ? "alert" : toast.status === "warn" ? "alert" : "check"
            color: toast.status === "bad" ? Q.bad : toast.status === "warn" ? Q.warn : Q.ok
            size: 18
            anchors.verticalCenter: parent.verticalCenter
        }
        Txt { text: toast.text; wrapMode: Text.NoWrap; lineHeight: 1.0; anchors.verticalCenter: parent.verticalCenter }
        Button { visible: toast.action.length > 0; kind: "quiet"; small: true; text: toast.action
                 anchors.verticalCenter: parent.verticalCenter; onClicked: toast.actionClicked() }
    }
}
