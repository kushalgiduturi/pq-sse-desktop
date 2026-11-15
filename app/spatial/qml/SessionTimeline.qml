// The recorded session as a row of marks. Each mark is one real event; choosing one
// replays it. The current one is larger and has a ring, so it does not rely on color.
import QtQuick

Item {
    id: tl
    property int current: -1
    signal chosen(int index)
    implicitHeight: 54

    Lbl { visible: events.count === 0; anchors.verticalCenter: parent.verticalCenter; text: T.stageTimelineEmpty; tone: "muted"; size: Theme.caption }
    ListView {
        id: list
        anchors.fill: parent
        orientation: ListView.Horizontal
        spacing: 4
        clip: true
        model: events.count
        onCountChanged: positionViewAtEnd()
        delegate: Item {
            id: mark
            required property int index
            readonly property var rec: events.records[index]
            readonly property bool on: index === tl.current
            width: 30; height: list.height
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: "Step " + (index + 1) + ": " + (rec ? rec.line : "")
            Keys.onReturnPressed: tl.chosen(index)
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: mark.on ? 4 : 9
                width: mark.on ? 26 : 16; height: width; radius: width / 2
                color: !rec ? Theme.glassStroke : rec.kind === "verify" ? Theme.ok : Theme.roleColor(rec.tag === "receiver" ? rec.who : rec.tag)
                opacity: rec && rec.scope === "practice" ? 0.45 : 1
                border.width: mark.on || mark.activeFocus ? 3 : 0
                border.color: Theme.textPrimary
                Behavior on width { NumberAnimation { duration: Theme.moveFast } }
            }
            Lbl {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                text: rec && rec.algorithm > 0 ? rec.algorithm : "·"
                size: Theme.caption * 0.9
                tone: mark.on ? "primary" : "muted"
            }
            HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: tl.chosen(mark.index) }
        }
    }
}
