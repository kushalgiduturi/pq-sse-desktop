// A character's mark: a colored disc with the first letter of the name. The cloud is a
// rounded square, so it differs from the people by shape as well as by color.
import QtQuick

Rectangle {
    id: avatar
    property string who: ""
    property real size: 44
    width: size; height: size
    radius: who.toLowerCase() === "cloud" ? size * 0.28 : size / 2
    color: Theme.roleColor(who)
    Accessible.role: Accessible.Graphic
    Accessible.name: who
    Text {
        anchors.centerIn: parent
        text: avatar.who.length ? avatar.who.charAt(0).toUpperCase() : "?"
        color: Theme.onRole
        font.family: Theme.fontFamily
        font.pixelSize: avatar.size * 0.42
        font.weight: Font.DemiBold
    }
}
