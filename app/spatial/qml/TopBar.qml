// The top bar: a depth-3 pill, 12 px from the window edges. The Story sentence on the left,
// then the engine status pill, the theme switch and the command palette button.
import QtQuick

Surface {
    id: bar
    property string story: ""
    property string engine: ""
    property string engineStatus: "neutral"
    property string themeLabel: ""
    property string searchLabel: ""
    property string searchKeys: ""
    property alias trailing: extra.data
    signal themeClicked()
    signal searchClicked()
    depth: 3
    radius: height / 2
    padding: 0
    height: Theme.barH
    activeFocusOnTab: false

    Row {
        id: left
        anchors.left: parent.left; anchors.leftMargin: Theme.sp5
        anchors.right: right.left; anchors.rightMargin: Theme.sp4
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.sp3
        Icon { name: "lock"; size: 18; color: Theme.text2; anchors.verticalCenter: parent.verticalCenter }
        Txt {
            width: parent.width - 30
            anchors.verticalCenter: parent.verticalCenter
            text: bar.story
            wrapMode: Text.NoWrap
            elide: Text.ElideRight
            lineHeight: 1.0
        }
    }
    Row {
        id: right
        anchors.right: parent.right; anchors.rightMargin: Theme.sp2
        anchors.verticalCenter: parent.verticalCenter
        spacing: Theme.sp2
        Item { id: extra; width: childrenRect.width; height: childrenRect.height; anchors.verticalCenter: parent.verticalCenter }
        Pill { visible: bar.engine.length > 0; text: bar.engine; status: bar.engineStatus; anchors.verticalCenter: parent.verticalCenter }
        Button {
            kind: "ghost"; small: true; icon: Theme.dark ? "sun" : "theme"; text: ""; minWidth: 40
            Accessible.name: bar.themeLabel
            anchors.verticalCenter: parent.verticalCenter
            onClicked: bar.themeClicked()
        }
        Button {
            id: search
            kind: "secondary"; small: true; icon: "search"; text: bar.searchLabel
            anchors.verticalCenter: parent.verticalCenter
            keys: bar.searchKeys
            onClicked: bar.searchClicked()
        }
    }
}
