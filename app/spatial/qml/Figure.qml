// A character on the Stage: neutral. A monochrome glyph in an inset disc, the name, and the
// position under it. No per-character colors: who is who is told by name and place.
import QtQuick

Column {
    id: fig
    property string name: ""
    property string role: ""
    property string glyph: "person"
    property bool active: false
    property real disc: 64
    spacing: Theme.sp2
    width: Math.max(disc, nameText.implicitWidth, roleText.implicitWidth)
    Accessible.role: Accessible.StaticText
    Accessible.name: fig.name + ", " + fig.role

    Item {
        width: fig.disc; height: fig.disc
        anchors.horizontalCenter: parent.horizontalCenter
        Surface { anchors.fill: parent; depth: 1; radius: width / 2; padding: 0 }
        Rectangle {
            visible: fig.active
            anchors.fill: parent; anchors.margins: -4
            radius: width / 2
            color: "transparent"; border.width: 1.5; border.color: Theme.text
        }
        Icon { anchors.centerIn: parent; name: fig.glyph; size: fig.disc * 0.44; color: Theme.text }
    }
    Txt { id: nameText; text: fig.name; strong: true; wrapMode: Text.NoWrap; anchors.horizontalCenter: parent.horizontalCenter; lineHeight: 1.2 }
    Txt { id: roleText; text: fig.role; kind: "sm"; tone: "secondary"; wrapMode: Text.NoWrap; anchors.horizontalCenter: parent.horizontalCenter; lineHeight: 1.2 }
}
