// Update: what the cloud sees when Alice adds and deletes documents.
// The rows of the cloud's store stay where they are. New entries land at brand-new
// addresses scattered through the store, with no line to the earlier search slip
// (forward privacy). A delete is one more masked entry: the cloud cannot tell which
// older entry it cancels (backward privacy); the deleted document's box fades.
// Counts come from the recorded event.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property var facts: record ? record.facts : ({})
    readonly property int adds: Math.min(4, parseInt(facts.adds) || 0)
    readonly property int deletes: Math.min(3, parseInt(facts.deletes) || 0)
    readonly property int fresh: Math.min(10, Math.max(adds + deletes, parseInt(facts.entries) || 0))
    readonly property real arrive: Math.max(0, Math.min(1, (progress - 0.15) / 0.40))
    readonly property bool slipShown: progress > 0.55
    readonly property bool deleteShown: progress > 0.70
    readonly property int cols: 10
    readonly property real cell: Math.min(30, (width - 120) / cols)
    // fixed spread of "new" positions so they are visibly not next to the old ones
    readonly property var spots: [37, 24, 33, 21, 29, 26, 38, 22, 35, 30]

    Lbl { text: T.updStore; size: Theme.caption; tone: "muted" }
    Grid {
        id: store
        y: 18
        columns: anim.cols
        spacing: 3
        Repeater {
            model: 40
            Rectangle {
                id: slot
                required property int index
                readonly property int newRank: anim.spots.indexOf(index)
                readonly property bool isNew: newRank >= 0 && newRank < anim.fresh
                readonly property bool isOld: index < 20 && !isNew
                readonly property bool landed: isNew && anim.arrive * anim.fresh > newRank
                width: anim.cell; height: 14; radius: 3
                color: landed ? Theme.tint(Theme.alice, 0.85) : isOld ? Theme.press : Theme.hover
                border.width: landed ? 1 : 0; border.color: Theme.textPrimary
                scale: landed && !Theme.reduceMotion ? 1 : (isNew ? 0.6 : 1)
                Behavior on scale { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
                Behavior on color { ColorAnimation { duration: Theme.base } }
            }
        }
    }
    // the earlier search slip only points at old rows: no line reaches the new ones
    Rectangle {
        visible: anim.slipShown
        x: store.x; y: store.y + store.height + 8
        width: slipText.implicitWidth + 16; height: 24; radius: 6
        color: Theme.bob
        Lbl { id: slipText; anchors.centerIn: parent; text: T.updOldSlip; color: Theme.onRole; size: Theme.caption; strong: true }
    }
    Rectangle {             // bracket over the old rows the slip can reach
        visible: anim.slipShown
        x: store.x; y: store.y - 3
        width: anim.cols * (anim.cell + 3) - 3; height: 2 * (14 + 3) + 3
        color: "transparent"; radius: 4
        border.width: 2; border.color: Theme.bob
    }
    // the delete: one more masked entry; the deleted box fades out
    Column {
        x: store.x + store.width + 14
        y: 18
        spacing: 6
        visible: anim.deletes > 0
        Lbl { text: T.updDeleted; size: Theme.caption; tone: "muted" }
        Rectangle {
            width: 40; height: 30; radius: 6
            color: Theme.press; border.width: 1; border.color: Theme.textSecondary
            opacity: anim.deleteShown ? 0.15 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.slow } }
            Lbl { anchors.centerIn: parent; text: anim.deleteShown ? "✕" : ""; color: Theme.fail; strong: true }
        }
    }
    Lbl {
        anchors.bottom: parent.bottom; width: parent.width
        size: Theme.caption; tone: "secondary"
        text: anim.deleteShown && anim.deletes > 0 ? T.updBackward
            : anim.slipShown ? T.updForward
            : Theme.fmt(T.updArrive, { n: anim.facts.entries !== undefined ? anim.facts.entries : anim.fresh })
    }
}
