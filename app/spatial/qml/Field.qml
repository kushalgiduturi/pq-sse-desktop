// A one-line field: a depth-1 inset, radius 14, 2 px ring on focus. Optional label above,
// help or error text below. An error shows a bad-colored ring and the message.
import QtQuick

Column {
    id: f
    property alias text: input.text
    property string label: ""
    property string hint: ""
    property string help: ""
    property string error: ""
    property bool secret: false
    property alias inputItem: input
    signal accepted()
    spacing: 6
    function clear() { input.text = "" }
    function focusInput() { input.forceActiveFocus() }

    Txt { visible: f.label.length > 0; text: f.label; kind: "sm"; strong: true }
    Item {
        width: f.width
        height: Theme.ctlH + 4
        Surface {
            anchors.fill: parent
            depth: 1
            padding: 0
            radius: Theme.rCtl
        }
        Rectangle {
            visible: input.activeFocus || f.error.length > 0
            anchors.fill: parent; anchors.margins: -2
            radius: Theme.rCtl + 2
            color: "transparent"
            border.width: 2
            border.color: f.error.length > 0 ? Theme.bad : Theme.ring
        }
        Txt {
            visible: input.text.length === 0
            anchors.verticalCenter: parent.verticalCenter
            x: 16; width: parent.width - 32
            text: f.hint
            tone: "tertiary"
            elide: Text.ElideRight; wrapMode: Text.NoWrap
        }
        TextInput {
            id: input
            anchors.fill: parent
            anchors.leftMargin: 16; anchors.rightMargin: 16
            verticalAlignment: TextInput.AlignVCenter
            clip: true
            color: f.enabled ? Theme.text : Theme.textDisabled
            selectionColor: Theme.accent
            selectedTextColor: Theme.accentInk
            font.family: Theme.ui
            font.pixelSize: Theme.fsMd
            echoMode: f.secret ? TextInput.Password : TextInput.Normal
            activeFocusOnTab: true
            selectByMouse: true
            Accessible.role: Accessible.EditableText
            Accessible.name: f.label.length > 0 ? f.label : f.hint
            Accessible.description: f.error.length > 0 ? f.error : f.help
            Accessible.passwordEdit: f.secret
            onAccepted: f.accepted()
        }
    }
    Txt {
        visible: text.length > 0
        width: f.width
        text: f.error.length > 0 ? f.error : f.help
        kind: "sm"
        tone: f.error.length > 0 ? "bad" : "secondary"
    }
}
