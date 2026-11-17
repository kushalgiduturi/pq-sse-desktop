// Buttons, sentence case. kind: primary (solid accent pill with a top highlight),
// secondary (glass pill), ghost (text only), danger (solid bad pill), quiet (small ghost).
// A loading button keeps its width: the label stays for layout and a spinner replaces it.
import QtQuick
import QtQuick.Effects

Item {
    id: b
    property string text: ""
    property string kind: "secondary"
    property string icon: ""
    property bool loading: false
    property bool small: false
    property real minWidth: 0
    property string keys: ""          // a shortcut shown after the label, in mono
    signal clicked()

    readonly property bool solid: kind === "primary" || kind === "danger"
    readonly property color solidColor: kind === "danger" ? Theme.badSolid : Theme.accent
    readonly property bool pressed: tap.pressed && enabled && !loading
    implicitHeight: small ? Math.max(32, Theme.ctlH - 8) : Theme.ctlH
    implicitWidth: Math.max(minWidth, row.implicitWidth + (kind === "ghost" || kind === "quiet" ? 20 : (small ? 28 : 40)))
    opacity: enabled ? 1 : 0.5
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: b.text
    Accessible.onPressAction: if (b.enabled && !b.loading) b.clicked()
    Keys.onReturnPressed: if (enabled && !loading) clicked()
    Keys.onEnterPressed: if (enabled && !loading) clicked()
    Keys.onSpacePressed: if (enabled && !loading) clicked()

    // press spring: a quick dip, released with one small overshoot
    scale: pressed ? 0.96 : 1
    Behavior on scale {
        enabled: !Theme.reduceMotion
        NumberAnimation { duration: Theme.dur2; easing.type: Easing.OutBack; easing.overshoot: Theme.pressOvershoot }
    }

    // accent shadow under solid buttons (neutral, never colored)
    Rectangle {
        visible: b.solid && !Theme.software
        z: -1
        x: 6; width: parent.width - 12
        y: Theme.shadowAccent[0] + (hover.hovered ? 2 : 0); height: parent.height
        radius: height / 2
        color: Theme.tint(Theme.shadowColor, Theme.shadowAccent[3] * (hover.hovered ? 1.1 : 0.8))
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 16 }
    }
    Rectangle {
        id: body
        anchors.fill: parent
        radius: height / 2
        color: b.solid ? (hover.hovered ? Qt.lighter(b.solidColor, 1.08) : b.solidColor)
             : b.kind === "secondary" ? (hover.hovered ? Theme.press : Theme.secondaryFill)
             : (hover.hovered || b.pressed ? Theme.hover : "transparent")
        Behavior on color { ColorAnimation { duration: Theme.dur1 } }
        border.width: b.kind === "secondary" ? 1 : 0
        border.color: Theme.hair
        // top highlight on solid and glass pills
        Rectangle {
            visible: b.solid || b.kind === "secondary"
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.leftMargin: parent.radius; anchors.rightMargin: parent.radius
            height: 1
            color: b.solid ? Theme.solidHighlight : Theme.edgeHi
        }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: b.pressed ? Theme.press : "transparent" }
    }
    // focus ring: 2 px, offset 2 px
    Rectangle {
        visible: b.activeFocus
        anchors.fill: parent; anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2; border.color: Theme.ring
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        opacity: b.loading ? 0 : 1
        Icon { visible: b.icon.length > 0; name: b.icon; size: 18; anchors.verticalCenter: parent.verticalCenter
               color: b.solid ? Theme.accentInk : b.kind === "ghost" || b.kind === "quiet" ? Theme.text2 : Theme.text }
        Txt {
            text: b.text
            kind: b.small || b.kind === "quiet" ? "sm" : "md"
            strong: true
            wrapMode: Text.NoWrap
            lineHeight: 1.0
            color: b.solid ? Theme.accentInk : b.kind === "ghost" || b.kind === "quiet" ? Theme.text2 : Theme.text
            anchors.verticalCenter: parent.verticalCenter
        }
        Txt { visible: b.keys.length > 0; text: b.keys; kind: "mono"; tone: "tertiary"; wrapMode: Text.NoWrap
              lineHeight: 1.0; anchors.verticalCenter: parent.verticalCenter }
    }
    // loading spinner: an arc that turns (a still arc with Reduce motion)
    Canvas {
        visible: b.loading
        anchors.centerIn: parent
        width: 18; height: 18
        onPaint: {
            var c = getContext("2d"); c.reset(); c.lineWidth = 2; c.lineCap = "round"
            c.strokeStyle = b.solid ? Theme.accentInk : Theme.text
            c.beginPath(); c.arc(9, 9, 7, 0, Math.PI * 1.4); c.stroke()
        }
        RotationAnimation on rotation { running: b.loading && !Theme.reduceMotion; loops: Animation.Infinite; from: 0; to: 360; duration: 900 }
    }
    HoverHandler { id: hover; enabled: b.enabled; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; enabled: b.enabled && !b.loading; onTapped: { b.forceActiveFocus(); b.clicked() } }
}
