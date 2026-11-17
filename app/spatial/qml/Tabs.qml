// Tabs: labels on the surface itself (no track), a soft pill slides under the selected one.
// Used for views inside one page; the segmented control is for a value choice.
import QtQuick

Item {
    id: tabs
    property var labels: []
    property int current: 0
    property string name: ""
    signal chosen(int index)
    implicitHeight: Theme.ctlH
    implicitWidth: row.implicitWidth
    activeFocusOnTab: true
    Accessible.role: Accessible.PageTabList
    Accessible.name: tabs.name
    Keys.onLeftPressed: if (current > 0) chosen(current - 1)
    Keys.onRightPressed: if (current < labels.length - 1) chosen(current + 1)

    readonly property Item sel: rep.count > current ? rep.itemAt(current) : null
    Rectangle {
        id: pill
        x: tabs.sel ? tabs.sel.x : 0
        width: tabs.sel ? tabs.sel.width : 0
        height: tabs.height
        radius: height / 2
        color: Theme.press
        Behavior on x { enabled: !Theme.reduceMotion; NumberAnimation { duration: Theme.dur4; easing.type: Easing.OutBack; easing.overshoot: Theme.springOvershoot } }
        Behavior on width { enabled: !Theme.reduceMotion; NumberAnimation { duration: Theme.dur4; easing.type: Easing.OutBack; easing.overshoot: Theme.springOvershoot } }
    }
    Rectangle {
        visible: tabs.activeFocus && tabs.sel !== null
        x: pill.x - 3; y: -3; width: pill.width + 6; height: tabs.height + 6
        radius: height / 2
        color: "transparent"; border.width: 2; border.color: Theme.ring
    }
    Row {
        id: row
        spacing: 2
        Repeater {
            id: rep
            model: tabs.labels
            Item {
                id: tab
                required property string modelData
                required property int index
                width: label.implicitWidth + 32
                height: tabs.height
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData
                Accessible.selected: index === tabs.current
                Txt {
                    id: label
                    anchors.centerIn: parent
                    text: tab.modelData
                    kind: "sm"
                    strong: tab.index === tabs.current
                    tone: tab.index === tabs.current ? "primary" : "secondary"
                    wrapMode: Text.NoWrap
                    lineHeight: 1.0
                }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: tabs.chosen(tab.index) }
            }
        }
    }
}
