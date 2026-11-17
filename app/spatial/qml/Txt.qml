// Text in the Quiet glass type scale. kind: display, xl, lg, md, sm, xs, metric, mono.
// tone: primary, secondary, tertiary, disabled, accent, ok, warn, bad.
import QtQuick

Text {
    property string kind: "md"
    property string tone: "primary"
    property bool strong: false
    readonly property bool isDisplay: kind === "display"
    color: tone === "secondary" ? Theme.text2 : tone === "tertiary" ? Theme.text3 : tone === "disabled" ? Theme.textDisabled
         : tone === "accent" ? Theme.accentText : tone === "ok" ? Theme.ok : tone === "warn" ? Theme.warn : tone === "bad" ? Theme.bad : Theme.text
    font.family: kind === "mono" ? Theme.mono : Theme.ui
    font.pixelSize: kind === "display" ? Theme.fsDisplay : kind === "xl" ? Theme.fsXl : kind === "lg" ? Theme.fsLg
                  : kind === "sm" || kind === "mono" ? Theme.fsSm : kind === "xs" ? Theme.fsXs : kind === "metric" ? Theme.fs2xl : Theme.fsMd
    font.weight: isDisplay || kind === "metric" ? Font.DemiBold : kind === "lg" || kind === "xl" || strong ? Font.DemiBold : Font.Normal
    font.letterSpacing: isDisplay ? Theme.fsDisplay * Theme.trackDisplay : 0
    lineHeight: isDisplay || kind === "metric" ? Theme.lhTight : Theme.lhBody
    wrapMode: Text.WordWrap
    linkColor: Theme.accentText
    textFormat: Text.PlainText
}
