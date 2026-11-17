// An empty state: a line icon in a soft disc, one plain sentence that says what is missing,
// one that says how to get it, and at most one button.
import QtQuick

Column {
    id: e
    property string icon: "empty"
    property string title: ""
    property string body: ""
    property string action: ""
    signal actionClicked()
    spacing: Q.sp2
    width: 360

    Rectangle {
        width: 48; height: 48; radius: 24
        color: Q.hover
        anchors.horizontalCenter: parent.horizontalCenter
        Icon { anchors.centerIn: parent; name: e.icon; size: 22; color: Q.text2 }
    }
    Item { width: 1; height: Q.sp1 }
    Txt { width: parent.width; text: e.title; strong: true; horizontalAlignment: Text.AlignHCenter }
    Txt { width: parent.width; text: e.body; kind: "sm"; tone: "secondary"; horizontalAlignment: Text.AlignHCenter }
    Item { width: 1; height: Q.sp2; visible: e.action.length > 0 }
    Button { visible: e.action.length > 0; text: e.action; kind: "secondary"; small: true
             anchors.horizontalCenter: parent.horizontalCenter; onClicked: e.actionClicked() }
}
