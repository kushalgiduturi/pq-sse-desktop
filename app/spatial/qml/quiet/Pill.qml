// Status pill: radius 999, a 12 percent tint of the status color, solid AA text and a
// small dot. Only for real status: ok, warn, bad, info, accent (e.g. GPU), neutral.
import QtQuick

Rectangle {
    id: p
    property string text: ""
    property string status: "neutral"
    readonly property color ink: status === "ok" ? Q.ok : status === "warn" ? Q.warn : status === "bad" ? Q.bad
                               : status === "info" ? Q.info : status === "accent" ? Q.accentText : Q.text2
    implicitHeight: label.implicitHeight + 6
    implicitWidth: label.implicitWidth + 28
    radius: height / 2
    color: status === "neutral" ? Q.hover : Q.tint(ink, 0.12)
    Accessible.role: Accessible.StaticText
    Accessible.name: p.text
    Rectangle { x: 10; anchors.verticalCenter: parent.verticalCenter; width: 6; height: 6; radius: 3; color: p.ink }
    Txt {
        id: label
        x: 20
        anchors.verticalCenter: parent.verticalCenter
        text: p.text
        kind: "xs"
        strong: true
        color: p.ink
        wrapMode: Text.NoWrap
        lineHeight: 1.2
    }
}
