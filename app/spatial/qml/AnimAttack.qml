// An attack: the attacker figure reaches for the item, the item cracks at the check that
// catches it, and that check is named. The list of checks is the real list the run
// reached; the one that stopped the attack carries a cross and its name in words.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property bool ran: record ? record.ran === true : false
    readonly property var checks: record && record.checks ? record.checks : []
    readonly property real reach: Math.max(0, Math.min(1, progress / 0.4))
    readonly property bool cracked: progress > 0.45
    readonly property bool named: progress > 0.7

    // the attacker (a picture, labeled as such under the panel)
    Avatar {
        id: attacker
        who: "attacker"
        x: 4 + anim.reach * (Theme.reduceMotion ? 0 : 46); y: 30
        size: 44
    }
    Lbl { x: 0; y: 80; text: T.attackFigure; size: Theme.caption; tone: "secondary" }

    // the item under attack
    Item {
        x: 128; y: 22; width: 78; height: 60
        Rectangle {
            x: anim.cracked && !Theme.reduceMotion ? -3 : 0
            width: 38; height: 60; radius: 8
            color: Theme.hover; border.width: 2
            border.color: anim.cracked ? Theme.bad : Theme.hairStrong
            rotation: anim.cracked && !Theme.reduceMotion ? -5 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
        }
        Rectangle {
            x: anim.cracked && !Theme.reduceMotion ? 43 : 38
            width: 38; height: 60; radius: 8
            color: Theme.hover; border.width: 2
            border.color: anim.cracked ? Theme.bad : Theme.hairStrong
            rotation: anim.cracked && !Theme.reduceMotion ? 5 : 0
            Behavior on rotation { NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
        }
        Icon { visible: anim.cracked; anchors.centerIn: parent; name: "cross"; size: 26; color: Theme.bad }
    }
    Lbl { x: 120; y: 86; width: 100; horizontalAlignment: Text.AlignHCenter; size: Theme.caption; tone: "secondary"
          text: anim.cracked ? T.attackCracked : T.attackItem }

    // the checks, in the order the run reached them
    Column {
        x: 236; y: 4
        width: parent.width - 240
        spacing: 3
        Lbl { visible: anim.checks.length === 0; width: parent.width; size: Theme.caption; tone: "secondary"
              text: anim.ran ? (anim.record.caughtBy ? Theme.fmt(T.attackStopped, { by: anim.record.caughtBy }) : "") : T.attackRunFirst }
        Repeater {
            model: anim.checks
            Row {
                id: line
                required property var modelData
                required property int index
                readonly property bool shown: anim.progress * (anim.checks.length + 1) > index + 0.5
                spacing: 6
                opacity: shown ? 1 : 0.3
                StatusMark { size: 14; state: !line.shown ? "pending" : line.modelData[1] ? "ok" : "bad"; anchors.verticalCenter: parent.verticalCenter }
                Lbl { text: line.shown && !line.modelData[1] ? Theme.fmt(T.attackCaughtHere, { name: line.modelData[0] }) : line.modelData[0]; size: Theme.caption
                      strong: line.shown && !line.modelData[1]; tone: line.shown ? "primary" : "muted" }
            }
        }
    }
}
