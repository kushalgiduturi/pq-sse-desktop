// Text in the Quiet glass type scale. kind: display, xl, lg, md, sm, xs, metric, mono.
// tone: primary, secondary, tertiary, disabled, accent, ok, warn, bad.
import QtQuick

Text {
    property string kind: "md"
    property string tone: "primary"
    property bool strong: false
    readonly property bool isDisplay: kind === "display"
    color: tone === "secondary" ? Q.text2 : tone === "tertiary" ? Q.text3 : tone === "disabled" ? Q.textDisabled
         : tone === "accent" ? Q.accentText : tone === "ok" ? Q.ok : tone === "warn" ? Q.warn : tone === "bad" ? Q.bad : Q.text
    font.family: kind === "mono" ? Q.mono : Q.ui
    font.pixelSize: kind === "display" ? Q.fsDisplay : kind === "xl" ? Q.fsXl : kind === "lg" ? Q.fsLg
                  : kind === "sm" || kind === "mono" ? Q.fsSm : kind === "xs" ? Q.fsXs : kind === "metric" ? Q.fs2xl : Q.fsMd
    font.weight: isDisplay || kind === "metric" ? Font.DemiBold : kind === "lg" || kind === "xl" || strong ? Font.DemiBold : Font.Normal
    font.letterSpacing: isDisplay ? Q.fsDisplay * Q.trackDisplay : 0
    lineHeight: isDisplay || kind === "metric" ? Q.lhTight : Q.lhBody
    wrapMode: Text.WordWrap
    linkColor: Q.accentText
    textFormat: Text.PlainText
}
