// A glass panel. "floating" panels (Story bar, dock, inspector, palette) sample the blurred
// room behind them and get a soft blurred shadow. Content panels are a strong tint with a
// rim and a cheap shadow: many of them are on screen at once, and text must stay readable
// whatever is behind. With the software renderer every panel is a flat tint.
import QtQuick
import QtQuick.Effects

Item {
    id: glass
    default property alias content: inner.data
    property real radius: Theme.rPanel
    property bool floating: false
    property real padding: Theme.s24
    property color rim: Theme.glassStroke
    property real rimWidth: 1
    property real fillOpacity: floating ? 0.72 : 0.86
    property real track: 0               // bind to a moving parent's position so the blur follows

    readonly property bool blurred: floating && !Theme.software && Theme.backdrop !== null

    Rectangle {
        visible: !Theme.software
        z: -2
        anchors.fill: parent
        anchors.topMargin: glass.floating ? 14 : 8
        anchors.leftMargin: 4; anchors.rightMargin: 4
        anchors.bottomMargin: glass.floating ? -14 : -8
        radius: glass.radius
        color: Theme.shadow
        opacity: glass.floating ? 0.30 : 0.16
        layer.enabled: glass.floating
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 36 }
    }
    ShaderEffectSource {
        id: sample
        visible: false
        live: glass.blurred
        sourceItem: glass.blurred ? Theme.backdrop : null
        sourceRect: {
            var follow = glass.x + glass.y + glass.width + glass.height + glass.track
            var p = glass.blurred ? glass.mapToItem(Theme.backdrop, 0, 0) : Qt.point(follow * 0, 0)
            return Qt.rect(p.x, p.y, glass.width, glass.height)
        }
    }
    Rectangle { id: shape; anchors.fill: parent; radius: glass.radius; visible: false; layer.enabled: glass.blurred }
    MultiEffect {
        visible: glass.blurred
        anchors.fill: parent
        source: sample
        maskEnabled: true
        maskSource: shape
    }
    Rectangle {
        anchors.fill: parent
        radius: glass.radius
        color: Theme.tint(Theme.glassFill, Theme.software ? 1.0 : glass.fillOpacity)
        border.width: glass.rimWidth
        border.color: Theme.tint(glass.rim, glass.rimWidth > 1 ? 1.0 : 0.6)
    }
    Item { id: inner; anchors.fill: parent; anchors.margins: glass.padding }
}
