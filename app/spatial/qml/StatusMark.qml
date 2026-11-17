// A check's state as a line mark: pending (a thin ring), ok (a check icon) or bad (a cross).
// The shape carries the meaning; the status color only supports it.
import QtQuick

Item {
    id: mark
    property string state: "pending"     // "pending", "ok", "bad"
    property real size: 16
    width: size; height: size
    Accessible.role: Accessible.StaticText
    Accessible.name: state === "ok" ? T.ok : state === "bad" ? T.failed : T.notChecked
    Rectangle {
        visible: mark.state === "pending"
        anchors.centerIn: parent
        width: mark.size * 0.75; height: width; radius: width / 2
        color: "transparent"; border.width: 1.5; border.color: Theme.hairStrong
    }
    Icon {
        visible: mark.state !== "pending"
        anchors.centerIn: parent
        size: mark.size
        name: mark.state === "ok" ? "check" : "cross"
        color: mark.state === "ok" ? Theme.ok : Theme.bad
        scale: Theme.reduceMotion ? 1 : (visible ? 1 : 0.8)
        Behavior on scale { NumberAnimation { duration: Theme.dur2; easing.type: Easing.OutBack; easing.overshoot: Theme.pressOvershoot } }
    }
}
