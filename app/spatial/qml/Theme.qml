// Design tokens: the only place where colors, sizes, radii and motion values are defined.
// Values match the Figma variables (docs/design/mockups.md).
pragma Singleton
import QtQuick

QtObject {
    // Set by Main.qml from the bridge.
    property bool dark: true
    property bool reduceMotion: false
    property bool software: false
    property real scale: 1.0
    readonly property bool large: scale > 1.3          // 150 % and 200 %: layouts stack and scroll instead of shrinking
    property Item backdrop: null          // the blurred copy of the room, sampled by floating glass
    property string fontFamily: "Segoe UI"
    property string monoFamily: "Consolas"

    // Color
    readonly property color roomTop: dark ? "#0E1626" : "#EAF0FA"
    readonly property color roomBottom: dark ? "#2A4368" : "#C9D8F0"
    readonly property color glassFill: dark ? "#22304A" : "#FFFFFF"
    readonly property color glassRaised: dark ? "#2C3D5C" : "#F4F7FC"
    readonly property color glassStroke: dark ? "#5E7397" : "#B7C4DA"
    readonly property color textPrimary: dark ? "#FFFFFF" : "#101828"
    readonly property color textSecondary: dark ? "#C9D6EA" : "#344054"
    readonly property color textMuted: dark ? "#9DB0CC" : "#52607A"
    readonly property color accent: dark ? "#6C9BFF" : "#1F5FD6"
    readonly property color accentOn: dark ? "#07142B" : "#FFFFFF"
    readonly property color alice: dark ? "#F2B544" : "#8A5A00"
    readonly property color bob: dark ? "#4CC9F0" : "#0B6E8E"
    readonly property color carol: dark ? "#C792EA" : "#7A3FB0"
    readonly property color cloud: dark ? "#9AA9BD" : "#4B5B73"
    readonly property color ok: dark ? "#4ADE80" : "#17703A"
    readonly property color fail: dark ? "#FF7A7A" : "#B42318"
    readonly property color warn: dark ? "#FFC857" : "#8A6500"
    readonly property color attacker: dark ? "#FF5C7A" : "#B4233F"
    readonly property color series1: dark ? "#3987e5" : "#2a78d6"     // chart: CPU (validated with the dataviz validator)
    readonly property color series2: dark ? "#d95926" : "#eb6834"     // chart: GPU
    readonly property color onRole: dark ? "#07142B" : "#FFFFFF"
    readonly property color shadow: dark ? "#000000" : "#31456B"

    // One color per character, everywhere. Other doctors alternate between the two doctor colors.
    function roleColor(name) {
        var key = String(name || "").toLowerCase()
        if (key === "alice" || key === "owner") return alice
        if (key === "cloud") return cloud
        if (key === "security" || key === "attacker") return attacker
        if (key === "bob" || key === "receiver") return bob
        if (key === "carol") return carol
        var sum = 0
        for (var i = 0; i < key.length; i++) sum += key.charCodeAt(i)
        return sum % 2 === 0 ? bob : carol
    }
    function tint(c, alpha) { return Qt.rgba(c.r, c.g, c.b, alpha) }
    // Fill {name} placeholders of a text from copy.py: Theme.fmt(T.stageMore, { n: 3 })
    function fmt(text, values) {
        var out = String(text)
        for (var key in values) out = out.split("{" + key + "}").join(String(values[key]))
        return out
    }

    // Type scale (pixels), scaled by the text size setting
    readonly property real caption: 12 * scale
    readonly property real body: 14 * scale
    readonly property real bodyLarge: 16 * scale
    readonly property real title: 20 * scale
    readonly property real headline: 28 * scale
    readonly property real display: 36 * scale

    // Space and shape
    readonly property int s4: 4
    readonly property int s8: 8
    readonly property int s12: 12
    readonly property int s16: 16
    readonly property int s24: 24
    readonly property int s32: 32
    readonly property int s48: 48
    readonly property int rChip: 12
    readonly property int rCard: 20
    readonly property int rPanel: 28
    readonly property int rDock: 30
    readonly property real controlHeight: 44 * Math.max(1, scale)

    // Motion: the only durations and curves in the app. Movement is off with Reduce motion;
    // fades stay, so state changes remain visible.
    readonly property int fast: 120
    readonly property int base: 220
    readonly property int slow: 360
    readonly property int stage: 600
    readonly property int stagger: 40
    readonly property int moveFast: reduceMotion ? 0 : fast
    readonly property int moveBase: reduceMotion ? 0 : base
    readonly property int moveSlow: reduceMotion ? 0 : slow
    readonly property real spring: 3.2
    readonly property real damping: 0.36
    readonly property real hoverSpring: 5.0
    readonly property real hoverDamping: 0.4
}
