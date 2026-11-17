// Verify: the checks tick one by one. A failed verification or a caught attack shows a
// cross at the check that caught it. Each line carries a mark shape and words.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property var steps: record ? record.steps : []
    readonly property bool failing: record ? (record.kind === "verify.failed" || record.kind.indexOf("attack") === 0) : false
    readonly property int reached: Math.floor(progress * steps.length + 0.0001)

    Column {
        anchors.fill: parent
        spacing: 3
        Repeater {
            model: anim.steps
            Row {
                id: line
                required property string modelData
                required property int index
                readonly property bool done: index < anim.reached || anim.progress >= 0.999
                readonly property bool bad: anim.failing && index === Math.min(1, anim.steps.length - 1)
                spacing: 8
                opacity: done ? 1 : 0.35
                Behavior on opacity { NumberAnimation { duration: Theme.base } }
                StatusMark { size: 16; state: !line.done ? "pending" : line.bad ? "bad" : "ok"; anchors.verticalCenter: parent.verticalCenter }
                Lbl {
                    width: anim.width - 28
                    text: line.modelData
                    size: Theme.caption
                    tone: line.done ? "primary" : "muted"
                    maximumLineCount: 2; elide: Text.ElideRight
                }
            }
        }
    }
}
