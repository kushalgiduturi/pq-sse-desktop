// A strip of numbers with thin vertical dividers. No capsule or card per number.
// items: [{value, label, tone}]
import QtQuick

Row {
    id: m
    property var items: []
    Repeater {
        model: m.items
        Item {
            id: cell
            required property var modelData
            required property int index
            width: m.width / Math.max(1, m.items.length)
            height: col.implicitHeight + 8
            Rectangle { visible: cell.index > 0; x: 0; y: 4; width: 1; height: parent.height - 8; color: Theme.hair }
            Column {
                id: col
                x: cell.index > 0 ? Theme.sp6 : 0
                width: parent.width - x - Theme.sp4
                spacing: 2
                Txt { text: cell.modelData.value; kind: "metric"; tone: cell.modelData.tone || "primary"; font.family: Theme.ui }
                Txt { width: parent.width; text: cell.modelData.label; kind: "sm"; tone: "secondary" }
            }
        }
    }
}
