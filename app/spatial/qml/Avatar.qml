// A character's mark: neutral. A monochrome glyph in an inset disc: a person, the cloud, or
// for the attacker an alert sign. Names are always shown next to it; no character has a color.
import QtQuick

Item {
    id: avatar
    property string who: ""
    property real size: 44
    property color color: Theme.text        // kept for older call sites: characters are neutral
    readonly property string key: who.toLowerCase()
    width: size; height: size
    Accessible.role: Accessible.Graphic
    Accessible.name: who
    Surface { anchors.fill: parent; depth: 1; radius: width / 2; padding: 0 }
    Icon {
        anchors.centerIn: parent
        size: avatar.size * 0.5
        name: avatar.key === "cloud" ? "cloud" : avatar.key === "attacker" || avatar.key === "security" ? "alert" : "person"
        color: avatar.key === "attacker" || avatar.key === "security" ? Theme.bad : Theme.text
    }
}
