// One-line text field.
import QtQuick

Rectangle {
    id: field
    property alias text: input.text
    property string hint: ""
    property bool secret: false
    signal accepted()

    implicitHeight: Theme.controlHeight
    implicitWidth: 220
    radius: 12
    color: Theme.tint(Theme.roomTop, Theme.dark ? 0.55 : 0.5)
    border.width: input.activeFocus ? 2 : 1
    border.color: input.activeFocus ? Theme.accent : Theme.tint(Theme.glassStroke, 0.8)

    function clear() { input.text = "" }
    function focusInput() { input.forceActiveFocus() }

    Text {
        visible: input.text.length === 0
        anchors.verticalCenter: parent.verticalCenter
        x: 14
        width: parent.width - 28
        elide: Text.ElideRight
        text: field.hint
        color: Theme.textMuted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.body
    }
    TextInput {
        id: input
        anchors.fill: parent
        anchors.leftMargin: 14; anchors.rightMargin: 14
        verticalAlignment: TextInput.AlignVCenter
        clip: true
        color: Theme.textPrimary
        selectionColor: Theme.accent
        selectedTextColor: Theme.accentOn
        font.family: Theme.fontFamily
        font.pixelSize: Theme.body
        echoMode: field.secret ? TextInput.Password : TextInput.Normal
        activeFocusOnTab: true
        selectByMouse: true
        Accessible.role: Accessible.EditableText
        Accessible.name: field.hint
        Accessible.passwordEdit: field.secret
        onAccepted: field.accepted()
    }
}
