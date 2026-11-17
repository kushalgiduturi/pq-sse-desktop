// Status pill: radius 999, a 12 percent tint of the status color, solid AA text and a
// small dot. Only for real status: ok, warn, bad, info, accent (e.g. GPU), neutral.
import QtQuick

Rectangle {
    id: p
    property string text: ""
    property string status: "neutral"
    property bool clickable: false        // a status that also opens its place (the engine opens Insights)
    signal clicked()
    readonly property color ink: status === "ok" ? Theme.ok : status === "warn" ? Theme.warn : status === "bad" ? Theme.bad
                               : status === "info" ? Theme.info : status === "accent" ? Theme.accentText : Theme.text2
    implicitHeight: label.implicitHeight + 6
    implicitWidth: label.implicitWidth + 28
    radius: height / 2
    color: status === "neutral" ? Theme.hover : Theme.tint(ink, 0.12)
    Accessible.role: clickable ? Accessible.Button : Accessible.StaticText
    Accessible.name: p.text
    activeFocusOnTab: clickable
    Keys.onReturnPressed: if (clickable) clicked()
    Keys.onSpacePressed: if (clickable) clicked()
    border.width: activeFocus ? 2 : 0
    border.color: Theme.ring
    HoverHandler { enabled: p.clickable; cursorShape: Qt.PointingHandCursor }
    TapHandler { enabled: p.clickable; onTapped: p.clicked() }
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
