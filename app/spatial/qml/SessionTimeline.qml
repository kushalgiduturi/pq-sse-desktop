// The recorded session as a row of short ticks. Each tick is one real event; choosing one
// replays it. The current one is taller and full strength, so it does not rely on color.
// Only real status is colored: a passed check (ok) and an attack (bad). Practice events are fainter.
import QtQuick

Item {
    id: tl
    property int current: -1
    signal chosen(int index)
    implicitHeight: 48

    Txt { visible: events.count === 0; anchors.verticalCenter: parent.verticalCenter; text: T.stageTimelineEmpty; tone: "tertiary"; kind: "sm" }
    ListView {
        id: list
        anchors.fill: parent
        orientation: ListView.Horizontal
        spacing: 2
        clip: true
        model: events.count
        onCountChanged: positionViewAtEnd()
        delegate: Item {
            id: mark
            required property int index
            readonly property var rec: events.records[index]
            readonly property bool on: index === tl.current
            width: Theme.touch ? 44 : 24; height: list.height
            activeFocusOnTab: true
            Accessible.role: Accessible.Button
            Accessible.name: Theme.fmt(T.stepN, { n: index + 1, text: rec ? rec.line : "" })
            Keys.onReturnPressed: tl.chosen(index)
            Keys.onSpacePressed: tl.chosen(index)
            Rectangle {
                anchors.fill: parent; anchors.bottomMargin: 16
                radius: Theme.rSm
                color: hov.hovered ? Theme.hover : "transparent"
                border.width: mark.activeFocus ? 2 : 0
                border.color: Theme.ring
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: mark.on ? 4 : 10
                width: 3; height: mark.on ? 24 : 14; radius: 1.5
                color: !mark.rec ? Theme.text3 : mark.rec.kind === "verify" ? Theme.ok
                     : mark.rec.tag === "security" ? Theme.bad : mark.on ? Theme.text : Theme.text3
                opacity: mark.rec && mark.rec.scope === "practice" ? 0.5 : 1
                Behavior on height { NumberAnimation { duration: Theme.dur1 } }
            }
            Txt {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                text: mark.rec && mark.rec.algorithm > 0 ? mark.rec.algorithm : ""
                kind: "mono"
                font.pixelSize: Theme.fsXs
                tone: mark.on ? "primary" : "tertiary"
                lineHeight: 1.0
            }
            HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: tl.chosen(mark.index) }
        }
    }
}
