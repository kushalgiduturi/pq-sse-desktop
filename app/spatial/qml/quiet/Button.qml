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
    readonly property color solidColor: kind === "danger" ? Q.badSolid : Q.accent
    readonly property bool pressed: tap.pressed && enabled && !loading
    implicitHeight: small ? Math.max(32, Q.ctlH - 8) : Q.ctlH
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
        enabled: !Q.reduceMotion
        NumberAnimation { duration: Q.dur2; easing.type: Easing.OutBack; easing.overshoot: Q.pressOvershoot }
    }

    // accent shadow under solid buttons (neutral, never colored)
    Rectangle {
        visible: b.solid && !Q.software
        z: -1
        x: 6; width: parent.width - 12
        y: Q.shadowAccent[0] + (hover.hovered ? 2 : 0); height: parent.height
        radius: height / 2
        color: Q.tint(Q.shadowColor, Q.shadowAccent[3] * (hover.hovered ? 1.1 : 0.8))
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 16 }
    }
    Rectangle {
        id: body
        anchors.fill: parent
        radius: height / 2
        color: b.solid ? (hover.hovered ? Qt.lighter(b.solidColor, 1.08) : b.solidColor)
             : b.kind === "secondary" ? Q.fill(3)
             : (hover.hovered || b.pressed ? Q.hover : "transparent")
        Behavior on color { ColorAnimation { duration: Q.dur1 } }
        // top highlight on solid and glass pills
        Rectangle {
            visible: b.solid || b.kind === "secondary"
            anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
            anchors.leftMargin: parent.radius * 0.6; anchors.rightMargin: parent.radius * 0.6
            height: 1
            color: b.solid ? Q.solidHighlight : Q.edgeHi
        }
        Rectangle { anchors.fill: parent; radius: parent.radius; color: b.pressed ? Q.press : "transparent" }
    }
    // focus ring: 2 px, offset 2 px
    Rectangle {
        visible: b.activeFocus
        anchors.fill: parent; anchors.margins: -3
        radius: height / 2
        color: "transparent"
        border.width: 2; border.color: Q.ring
    }
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        opacity: b.loading ? 0 : 1
        Icon { visible: b.icon.length > 0; name: b.icon; size: 18; anchors.verticalCenter: parent.verticalCenter
               color: b.solid ? Q.accentInk : b.kind === "ghost" || b.kind === "quiet" ? Q.text2 : Q.text }
        Txt {
            text: b.text
            kind: b.small || b.kind === "quiet" ? "sm" : "md"
            strong: true
            wrapMode: Text.NoWrap
            lineHeight: 1.0
            color: b.solid ? Q.accentInk : b.kind === "ghost" || b.kind === "quiet" ? Q.text2 : Q.text
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
            c.strokeStyle = b.solid ? Q.accentInk : Q.text
            c.beginPath(); c.arc(9, 9, 7, 0, Math.PI * 1.4); c.stroke()
        }
        RotationAnimation on rotation { running: b.loading && !Q.reduceMotion; loops: Animation.Infinite; from: 0; to: 360; duration: 900 }
    }
    HoverHandler { id: hover; enabled: b.enabled; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: tap; enabled: b.enabled && !b.loading; onTapped: { b.forceActiveFocus(); b.clicked() } }
}
