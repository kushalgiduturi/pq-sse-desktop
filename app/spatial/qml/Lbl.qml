// Text with the app's defaults. "tone" picks the color token: primary, secondary, muted.
import QtQuick

Text {
    property string tone: "primary"
    property real size: Theme.body
    property bool strong: false
    color: tone === "muted" ? Theme.textMuted : tone === "secondary" ? Theme.textSecondary : Theme.textPrimary
    font.family: Theme.fontFamily
    font.pixelSize: size
    font.weight: strong ? Font.DemiBold : Font.Normal
    wrapMode: Text.WordWrap
    linkColor: Theme.accent
    lineHeight: 1.25
}
