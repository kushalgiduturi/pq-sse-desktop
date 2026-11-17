// A switch with its label on the left: an inset track, a raised knob that slides with the
// spring. On: the track takes the accent.
import QtQuick

Item {
    id: sw
    property string text: ""
    property string help: ""
    property bool checked: false
    signal toggled(bool on)
    implicitHeight: Math.max(Q.ctlH, col.implicitHeight)
    implicitWidth: 360
    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: sw.text
    Accessible.checkable: true
    Accessible.checked: sw.checked
    Accessible.onToggleAction: sw.toggled(!sw.checked)
    Keys.onSpacePressed: toggled(!checked)
    Keys.onReturnPressed: toggled(!checked)

    Column {
        id: col
        anchors.left: parent.left; anchors.right: track.left; anchors.rightMargin: Q.sp4
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Txt { width: parent.width; text: sw.text }
        Txt { visible: sw.help.length > 0; width: parent.width; text: sw.help; kind: "sm"; tone: "secondary" }
    }
    Item {
        id: track
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
        width: 44; height: 26
        Surface { anchors.fill: parent; depth: 1; radius: height / 2; padding: 0; visible: !sw.checked }
        Rectangle { anchors.fill: parent; radius: height / 2; color: Q.accent; visible: sw.checked }
        Rectangle {
            x: sw.checked ? parent.width - width - 3 : 3
            y: 3; width: 20; height: 20; radius: 10
            color: sw.checked ? Q.accentInk : Q.knobOff
            border.width: Q.dark || sw.checked ? 0 : 1
            border.color: Q.hairStrong
            Behavior on x { enabled: !Q.reduceMotion; NumberAnimation { duration: Q.dur3; easing.type: Easing.OutBack; easing.overshoot: Q.springOvershoot } }
        }
        Rectangle {
            visible: sw.activeFocus
            anchors.fill: parent; anchors.margins: -3
            radius: height / 2
            color: "transparent"; border.width: 2; border.color: Q.ring
        }
    }
    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { onTapped: { sw.forceActiveFocus(); sw.toggled(!sw.checked) } }
}
