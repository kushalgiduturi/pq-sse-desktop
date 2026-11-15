// A modal sheet used for the three-part error message and for a glossary entry.
import QtQuick

Item {
    id: sheet
    property bool open: false
    property string title: ""
    property var rows: []                 // [{head, body}]
    property string technical: ""
    property bool error: false
    property bool copied: false
    property string closeText: T.close
    property string actionText: ""        // an optional second, filled button
    signal action()
    signal dismissed()

    anchors.fill: parent
    visible: opacity > 0.01
    opacity: open ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    function show() { copied = false; open = true; closeButton.forceActiveFocus() }
    Keys.onEscapePressed: open = false

    Rectangle { anchors.fill: parent; color: Theme.tint(Theme.roomTop, 0.55); TapHandler { onTapped: sheet.open = false } }
    Glass {
        floating: true
        rim: sheet.error ? Theme.fail : Theme.glassStroke
        rimWidth: sheet.error ? 2 : 1
        width: Math.min(640, parent.width - 80)
        height: body.implicitHeight + 2 * padding
        anchors.centerIn: parent
        Accessible.role: Accessible.AlertMessage
        Accessible.name: sheet.title
        Column {
            id: body
            width: parent.width
            spacing: 14
            Row {
                spacing: 10
                Lbl { visible: sheet.error; text: "✕"; color: Theme.fail; size: Theme.title; strong: true }
                Lbl { text: sheet.title; size: Theme.title; strong: true; width: body.width - 40 }
            }
            Repeater {
                model: sheet.rows
                Column {
                    required property var modelData
                    width: body.width
                    spacing: 2
                    Lbl { text: modelData.head; tone: "muted"; size: Theme.caption; strong: true; visible: text.length > 0 }
                    Lbl { text: modelData.body; width: parent.width; tone: "secondary"; size: Theme.bodyLarge * 0.95 }
                }
            }
            Row {
                spacing: 10
                PButton { visible: sheet.actionText.length > 0; text: sheet.actionText; primary: true; onClicked: { sheet.open = false; sheet.action() } }
                PButton { id: closeButton; text: sheet.closeText; primary: sheet.actionText.length === 0; onClicked: { sheet.open = false; sheet.dismissed() } }
                PButton {
                    visible: sheet.technical.length > 0
                    text: sheet.copied ? T.errorCopied : T.errorCopy
                    onClicked: { app.copyText(sheet.technical); sheet.copied = true }
                }
            }
        }
    }
}
