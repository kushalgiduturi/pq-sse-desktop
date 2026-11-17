// A modal sheet (the three-part error message, a glossary entry, the welcome): a dim backdrop,
// never blurred, and a depth-4 surface with radius 28 and a dense fill.
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
    function show() { copied = false; open = true; (actionText.length > 0 ? actionButton : closeButton).forceActiveFocus() }
    Keys.onEscapePressed: { open = false; dismissed() }

    Rectangle { anchors.fill: parent; color: Theme.dim; TapHandler { onTapped: sheet.open = false } }
    Glass {
        floating: true
        blur: false
        radius: Theme.rPanel
        padding: Theme.sp8
        width: Math.min(600, parent.width - 80)
        scale: sheet.open ? 1 : 0.96
        Behavior on scale { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
        height: body.implicitHeight + 2 * padding
        anchors.centerIn: parent
        Accessible.role: Accessible.AlertMessage
        Accessible.name: sheet.title
        Column {
            id: body
            width: parent.width
            spacing: Theme.sp3
            Row {
                spacing: Theme.sp3
                Icon { visible: sheet.error; name: "alert"; color: Theme.bad; size: 22; anchors.verticalCenter: parent.verticalCenter }
                Txt { text: sheet.title; kind: "xl"; width: body.width - (sheet.error ? 34 : 0) }
            }
            Repeater {
                model: sheet.rows
                Column {
                    required property var modelData
                    width: body.width
                    spacing: 2
                    Txt { text: modelData.head; kind: "sm"; strong: true; visible: text.length > 0 }
                    Txt { text: modelData.body; width: parent.width; tone: "secondary" }
                }
            }
            Item { width: 1; height: Theme.sp2 }
            Flow {
                width: parent.width
                spacing: Theme.sp2
                PButton { id: actionButton; visible: sheet.actionText.length > 0; text: sheet.actionText; primary: true; onClicked: { sheet.open = false; sheet.action() } }
                PButton { id: closeButton; text: sheet.closeText; primary: sheet.actionText.length === 0; quiet: sheet.actionText.length > 0; onClicked: { sheet.open = false; sheet.dismissed() } }
                PButton {
                    visible: sheet.technical.length > 0
                    text: sheet.copied ? T.errorCopied : T.errorCopy
                    onClicked: { app.copyText(sheet.technical); sheet.copied = true }
                }
            }
        }
    }
}
