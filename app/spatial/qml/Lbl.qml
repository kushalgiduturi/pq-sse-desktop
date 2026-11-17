// Older text item, now on the Quiet glass type: tone primary, secondary or muted.
import QtQuick

Text {
    property string tone: "primary"
    property real size: Theme.fsMd
    property bool strong: false
    color: tone === "muted" ? Theme.text3 : tone === "secondary" ? Theme.text2 : Theme.text
    font.family: Theme.ui
    font.pixelSize: size
    font.weight: strong ? Font.DemiBold : Font.Normal
    wrapMode: Text.WordWrap
    linkColor: Theme.accentText
    lineHeight: size >= Theme.fsXl ? Theme.lhTight : 1.4
    textFormat: Text.PlainText
}
