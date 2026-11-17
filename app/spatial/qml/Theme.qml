// Quiet glass design tokens, ported from Hastra assets/css/theme-spatial.css.
// The only place where colors, sizes, radii, shadows and durations are defined.
pragma Singleton
import QtQuick

QtObject {
    id: q
    // ------------------------------------------------------------------ state (set by the window)
    property bool dark: true
    property bool software: false          // software renderer: no blur, dense fills, no light, no tilt
    property bool reduceTransparency: false
    property bool reduceMotion: false
    property bool touch: false
    property real scale: 1.0
    property Item backdrop: null           // the blurred world, sampled by glass at depth 2 to 4
    property string ui: "Onest"
    property string mono: "Share Tech Mono"

    readonly property bool blurOn: !software && !reduceTransparency && backdrop !== null
    readonly property bool still: reduceMotion || software || touch

    function rgba(r, g, b, a) { return Qt.rgba(r / 255, g / 255, b / 255, a) }
    function tint(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
    function fmt(text, values) {
        var out = String(text)
        for (var key in values) out = out.split("{" + key + "}").join(String(values[key]))
        return out
    }

    // ------------------------------------------------------------------ type
    readonly property real fsXs: 12 * scale
    readonly property real fsSm: 13 * scale
    readonly property real fsMd: 15 * scale
    readonly property real fsLg: 18 * scale
    readonly property real fsXl: 24 * scale
    readonly property real fs2xl: 32 * scale
    readonly property real fsDisplay: 40 * scale
    readonly property real lhBody: 1.55
    readonly property real lhTight: 1.1
    readonly property real trackDisplay: -0.025       // em

    // ------------------------------------------------------------------ space and shape
    readonly property int sp1: 4
    readonly property int sp2: 8
    readonly property int sp3: 12
    readonly property int sp4: 16
    readonly property int sp5: 20
    readonly property int sp6: 24
    readonly property int sp8: 32
    readonly property int sp10: 40
    readonly property int sp12: 48
    readonly property int sp16: 64
    readonly property int barInset: 12
    readonly property int barH: 56
    readonly property int pageMax: 1180
    readonly property int rPanel: 28
    readonly property int rFloat: 24
    readonly property int rCard: 16
    readonly property int rCtl: 14
    readonly property int rSm: 10
    readonly property real ctlH: Math.max(touch ? 44 : 40, 40 * Math.min(scale, 1.4))

    // ------------------------------------------------------------------ brand and text
    readonly property color accent: dark ? "#e50914" : "#2563eb"
    readonly property color accentText: dark ? "#ff4655" : "#1e40af"
    readonly property color accentInk: "#ffffff"
    readonly property color ring: dark ? "#ff4655" : "#2563eb"
    readonly property color text: dark ? "#ffffff" : "#000000"
    readonly property color text2: dark ? rgba(255, 255, 255, .76) : "#2b3442"
    readonly property color text3: dark ? rgba(255, 255, 255, .62) : "#3d4756"
    readonly property color textDisabled: dark ? rgba(255, 255, 255, .5) : "#6b7484"

    // ------------------------------------------------------------------ status
    readonly property color ok: dark ? "#4ade80" : "#166534"
    readonly property color warn: dark ? "#fbbf24" : "#92400e"
    readonly property color bad: dark ? "#ff6b76" : "#a51d2d"
    readonly property color badSolid: dark ? "#d42033" : "#c62031"
    readonly property color info: dark ? "#67e8f9" : "#155e75"

    // ------------------------------------------------------------------ lines
    readonly property color hair: dark ? rgba(255, 255, 255, .09) : rgba(15, 23, 42, .10)
    readonly property color hairStrong: dark ? rgba(255, 255, 255, .16) : rgba(15, 23, 42, .18)
    readonly property color hover: dark ? rgba(255, 255, 255, .06) : rgba(15, 23, 42, .05)
    readonly property color press: dark ? rgba(255, 255, 255, .10) : rgba(15, 23, 42, .09)
    readonly property color rowHover: dark ? rgba(255, 255, 255, .04) : rgba(15, 23, 42, .035)
    // raised pill inside a track (segmented control, switch knob) and its contact shade
    readonly property color raised: dark ? rgba(255, 255, 255, .12) : "#ffffff"
    readonly property color raisedShade: dark ? rgba(0, 0, 0, 0) : rgba(15, 23, 42, .10)
    readonly property color knobOff: dark ? rgba(255, 255, 255, .72) : "#ffffff"
    readonly property color secondaryFill: dark ? rgba(255, 255, 255, .07) : rgba(255, 255, 255, .9)   // glass pill button
    readonly property color solidHighlight: rgba(255, 255, 255, .28)   // top line on solid buttons
    readonly property color transparent: rgba(0, 0, 0, 0)

    // ------------------------------------------------------------------ fills by depth (glass, then dense)
    readonly property var glassFills: dark
        ? [rgba(0, 0, 0, 0), rgba(9, 10, 14, .46), rgba(10, 11, 16, .64), rgba(18, 20, 27, .72), rgba(14, 15, 20, .86)]
        : [rgba(0, 0, 0, 0), rgba(15, 23, 42, .05), rgba(255, 255, 255, .74), rgba(255, 255, 255, .80), rgba(255, 255, 255, .92)]
    readonly property var solidFills: dark
        ? [rgba(0, 0, 0, 0), rgba(12, 13, 18, .90), rgba(12, 13, 18, .94), rgba(20, 22, 29, .96), rgba(16, 17, 23, .98)]
        : [rgba(0, 0, 0, 0), rgba(241, 244, 248, .96), rgba(250, 251, 253, .97), rgba(255, 255, 255, .98), "#ffffff"]
    function fill(depth) { return blurOn ? glassFills[depth] : solidFills[depth] }
    // depth 1 (insets) is never blurred, so it always uses the glass value
    function insetFill() { return glassFills[1] }
    readonly property var blurs: [0, 0, 18, 16, 20]

    // ------------------------------------------------------------------ edge and shadow
    readonly property color edgeHi: dark ? rgba(255, 255, 255, .14) : rgba(255, 255, 255, .95)
    readonly property color edgeSide: dark ? rgba(255, 255, 255, .06) : rgba(255, 255, 255, .5)
    readonly property color edgeLo: dark ? rgba(255, 255, 255, .03) : rgba(15, 23, 42, .06)
    readonly property color insetShade: dark ? rgba(0, 0, 0, .28) : rgba(15, 23, 42, .10)
    // shadows: [offsetY, blur, spread, alpha] for the long soft one, then the short contact one
    readonly property color shadowColor: dark ? "#000000" : "#0f172a"
    readonly property var shadows: dark
        ? [null, null, [24, 60, -18, .65, 2, 6, .35], [14, 34, -10, .60, 1, 3, .40], [28, 70, -16, .72, 4, 12, .40]]
        : [null, null, [24, 60, -20, .28, 2, 6, .08], [12, 30, -10, .25, 1, 3, .08], [28, 70, -18, .32, 4, 12, .10]]
    readonly property var shadowAccent: dark ? [6, 16, -6, .6] : [6, 16, -6, .3]

    // ------------------------------------------------------------------ world (depth 0) and dim
    readonly property color world: dark ? "#07080b" : "#eef2f7"
    readonly property color worldEdge: dark ? "#020203" : "#dde4ee"
    readonly property color worldInk: dark ? rgba(255, 255, 255, .10) : rgba(15, 23, 42, .12)
    readonly property color worldWash: dark ? rgba(255, 255, 255, .045) : rgba(255, 255, 255, .85)
    readonly property real worldBlur: 20                // the one blur pass every glass surface samples (never above 24)
    readonly property color dim: dark ? rgba(3, 4, 7, .40) : rgba(15, 23, 42, .28)
    readonly property color glow: dark ? rgba(255, 255, 255, .07) : rgba(255, 255, 255, .55)
    readonly property real glowSize: 420
    readonly property real tiltMax: still ? 0 : 3

    // ------------------------------------------------------------------ motion
    readonly property int dur1: reduceMotion ? 0 : 150
    readonly property int dur2: reduceMotion ? 0 : 220
    readonly property int dur3: reduceMotion ? 0 : 280
    readonly property int dur4: reduceMotion ? 0 : 350
    // ease-out cubic-bezier(.16, 1, .3, 1)
    readonly property var easeOutCurve: [0.16, 1.0, 0.3, 1.0, 1.0, 1.0]
    readonly property real springOvershoot: 0.8         // spring 280 / 25 / .8: about 4 percent past the target
    readonly property real pressOvershoot: 1.6          // press 550 / 15 / 1.1: about 8 percent

    // ------------------------------------------------------------------ older names, kept so every page
    // reads the same tokens. Characters are neutral: no character has a color of its own.
    readonly property bool large: scale > 1.3          // 150 % and 200 %: layouts stack and scroll instead of shrinking
    property string fontFamily: ui
    property string monoFamily: mono
    readonly property color roomTop: world
    readonly property color roomBottom: worldEdge
    readonly property color glassFill: fill(3)
    readonly property color glassRaised: hover
    readonly property color glassStroke: hairStrong
    readonly property color textPrimary: text
    readonly property color textSecondary: text2
    readonly property color textMuted: text3
    readonly property color accentOn: accentInk
    readonly property color alice: text
    readonly property color bob: text
    readonly property color carol: text
    readonly property color cloud: text
    readonly property color attacker: bad
    readonly property color fail: bad
    readonly property color onRole: dark ? "#000000" : "#ffffff"
    readonly property color shadow: shadowColor
    readonly property color series1: accent               // charts: the measured series in accent
    readonly property color series2: text2                // and the comparison in text-2
    function roleColor(name) { return String(name || "").toLowerCase() === "attacker" ? bad : text }

    readonly property real caption: fsXs
    readonly property real body: fsMd
    readonly property real bodyLarge: fsMd
    readonly property real title: fsLg
    readonly property real headline: fsXl
    readonly property real display: fsDisplay

    readonly property int s4: sp1
    readonly property int s8: sp2
    readonly property int s12: sp3
    readonly property int s16: sp4
    readonly property int s24: sp6
    readonly property int s32: sp8
    readonly property int s48: sp12
    readonly property int rChip: rSm
    readonly property int rDock: rFloat
    readonly property real controlHeight: ctlH

    readonly property int fast: 150
    readonly property int base: 220
    readonly property int slow: 350
    readonly property int stage: 600
    readonly property int stagger: 40
    readonly property int moveFast: dur1
    readonly property int moveBase: dur2
    readonly property int moveSlow: dur4
    readonly property real spring: 3.2
    readonly property real damping: 0.36
    readonly property real hoverSpring: 5.0
    readonly property real hoverDamping: 0.4
}
