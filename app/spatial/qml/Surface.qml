// A Quiet glass surface at depth 1 to 4.
//   1  inset (fields, tracks, wells): never blurred, inner shade, no shadow
//   2  the page panel: blur 18
//   3  top bar and raised controls: blur 16
//   4  dock, drawers, dialogs, popovers, toasts: blur 20
// Depth comes from fill, edge and shadow, never from color. Every surface carries the
// specular edge (bright top, dim sides, dimmer bottom). The shadow is neutral and only
// drawn outside the surface, as a CSS box-shadow would be. Never put a Surface of depth 2
// to 4 inside another one: scripts/craft_check.py fails on that.
import QtQuick
import QtQuick.Effects

Item {
    id: s
    property int depth: 2
    property real radius: depth === 2 ? Theme.rPanel : depth === 4 ? Theme.rFloat : depth === 1 ? Theme.rCtl : Theme.rPanel
    property bool blur: depth >= 2                 // a depth-4 dialog sets this to false (dense fill)
    property bool pointerLight: false              // only the page panel uses it
    property real padding: depth === 2 ? Math.max(Theme.sp5, Math.min(Theme.sp10, width * 0.03)) : Theme.sp4
    property real track: 0                         // bind to a moving ancestor's position so the blur follows
    default property alias content: inner.data

    readonly property bool blurred: blur && depth >= 2 && Theme.blurOn
    readonly property var sh: depth >= 2 && !Theme.software ? Theme.shadows[depth] : null
    readonly property color fillColor: depth === 1 ? Theme.insetFill() : (blurred ? Theme.glassFills[depth] : Theme.solidFills[depth])

    // ---------------------------------------------------------------- shadow, outside only
    Item {
        id: shadowBox
        visible: s.sh !== null
        readonly property real m: s.sh ? s.sh[1] + Math.abs(s.sh[0]) + 8 : 0
        x: -m; y: -m; width: s.width + 2 * m; height: s.height + 2 * m
        z: -1
        layer.enabled: visible
        layer.effect: MultiEffect {
            maskEnabled: true
            maskInverted: true
            maskSource: hole
            maskThresholdMin: 0.5
            maskSpreadAtMin: 0.0
        }
        Rectangle {        // long, soft shadow
            x: shadowBox.m - (s.sh ? s.sh[2] : 0)
            y: shadowBox.m + (s.sh ? s.sh[0] - s.sh[2] : 0)
            width: s.width + 2 * (s.sh ? s.sh[2] : 0); height: s.height + 2 * (s.sh ? s.sh[2] : 0)
            radius: s.radius
            color: Theme.tint(Theme.shadowColor, s.sh ? s.sh[3] : 0)
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: s.sh ? Math.round(s.sh[1] / 2) : 0 }
        }
        Rectangle {        // short contact shadow
            x: shadowBox.m
            y: shadowBox.m + (s.sh ? s.sh[4] : 0)
            width: s.width; height: s.height
            radius: s.radius
            color: Theme.tint(Theme.shadowColor, s.sh ? s.sh[6] : 0)
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: s.sh ? Math.max(2, s.sh[5]) : 0 }
        }
    }
    Item {
        id: hole
        visible: false
        layer.enabled: true
        width: shadowBox.width; height: shadowBox.height
        Rectangle { x: shadowBox.m; y: shadowBox.m; width: s.width; height: s.height; radius: s.radius; color: "black" }
    }

    // ---------------------------------------------------------------- blurred world under the glass
    ShaderEffectSource {
        id: sample
        visible: false
        live: s.blurred
        sourceItem: s.blurred ? Theme.backdrop : null
        sourceRect: {
            var follow = s.x + s.y + s.width + s.height + s.track
            var p = s.blurred && Theme.backdrop ? s.mapToItem(Theme.backdrop, 0, 0) : Qt.point(follow * 0, 0)
            return Qt.rect(p.x, p.y, s.width, s.height)
        }
    }
    Rectangle { id: shape; anchors.fill: parent; radius: s.radius; visible: false; layer.enabled: s.blurred }
    MultiEffect {
        visible: s.blurred
        anchors.fill: parent
        source: sample
        maskEnabled: true
        maskSource: shape
        saturation: Theme.dark ? 0.3 : 0.5
    }

    // ---------------------------------------------------------------- fill
    Rectangle {
        anchors.fill: parent
        radius: s.radius
        color: s.fillColor
    }
    // inset shade for depth 1: a dark top band fading down, inside the rounded shape
    Rectangle {
        visible: s.depth === 1
        anchors.fill: parent
        radius: s.radius
        gradient: Gradient {
            GradientStop { position: 0.0; color: Theme.insetShade }
            GradientStop { position: 0.12; color: "transparent" }
        }
    }

    // ---------------------------------------------------------------- pointer light (page panel only)
    Item {
        id: lightBox
        anchors.fill: parent
        visible: s.pointerLight && !Theme.still && hover.hovered
        clip: true
        Rectangle {
            width: Theme.glowSize; height: Theme.glowSize; radius: Theme.glowSize / 2
            x: hover.point.position.x - width / 2
            y: hover.point.position.y - height / 2
            gradient: Gradient {
                orientation: Gradient.Vertical
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 0.5; color: Theme.glow }
                GradientStop { position: 1.0; color: "transparent" }
            }
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
        }
    }
    HoverHandler { id: hover; enabled: s.pointerLight }

    // ---------------------------------------------------------------- specular edge
    Item {
        id: edge
        anchors.fill: parent
        visible: s.depth >= 2 || Theme.dark
        layer.enabled: true
        layer.effect: MultiEffect { maskEnabled: true; maskSource: ring; maskThresholdMin: 0.5 }
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.edgeHi }
                GradientStop { position: Math.min(0.5, s.radius * 1.2 / Math.max(1, s.height)); color: Theme.edgeSide }
                GradientStop { position: 1.0; color: Theme.edgeLo }
            }
        }
    }
    Item {
        id: ring
        visible: false
        layer.enabled: true
        width: s.width; height: s.height
        Rectangle { anchors.fill: parent; radius: s.radius; color: "transparent"; border.width: 1; border.color: "black" }
    }

    Item { id: inner; anchors.fill: parent; anchors.margins: s.padding }
}
