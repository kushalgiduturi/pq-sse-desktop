// Signing (ML-DSA): a stamp presses onto the content and leaves a mark tied to it; a
// magnifier then checks the mark. Below, a changed copy visibly fails the same check.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property real press: Math.max(0, Math.min(1, progress / 0.35))
    readonly property bool marked: progress > 0.35
    readonly property real scan: Math.max(0, Math.min(1, (progress - 0.45) / 0.35))
    readonly property bool verdict: progress > 0.82
    readonly property color who: Theme.roleColor(record ? (record.tag === "receiver" ? record.who : record.tag) : "alice")

    component Paper: Rectangle {
        property bool tampered: false
        width: 150; height: 78; radius: 10
        color: Theme.hover
        border.width: 1; border.color: Theme.hairStrong
        Column {
            x: 10; y: 10; spacing: 6
            Repeater {
                model: 4
                Rectangle {
                    required property int index
                    width: [110, 90, 120, 70][index]; height: 5; radius: 2
                    color: parent.parent.tampered && index === 1 ? Theme.fail : Theme.textMuted
                }
            }
        }
    }

    Paper { id: genuine; x: 4; y: 8 }
    Paper { id: changed; x: 4; y: 96; tampered: true; opacity: anim.scan > 0 ? 1 : 0.35 }
    Lbl { x: 162; y: 8; width: parent.width - 166; size: Theme.caption; tone: "secondary"
          text: anim.record ? Theme.fmt(T.signGenuine, { title: anim.record.title }) : "" }
    Lbl { x: 162; y: 96; width: parent.width - 166; size: Theme.caption; tone: "secondary"; text: T.signChanged }

    // the stamp
    Rectangle {
        x: 84; y: 30 - (1 - anim.press) * (Theme.reduceMotion ? 0 : 46)
        width: 56; height: 30; radius: 6
        color: Theme.tint(anim.who, anim.marked ? 0.0 : 0.9)
        border.width: 2; border.color: anim.who
        rotation: -8
        opacity: anim.progress > 0.02 ? 1 : 0
        Lbl { anchors.centerIn: parent; text: anim.marked ? T.signSigned : T.signStamp; color: anim.marked ? anim.who : Theme.accentOn; size: Theme.caption; strong: true }
    }
    Rectangle {          // the copied mark on the changed sheet
        x: 84; y: 118; width: 56; height: 30; radius: 6
        color: "transparent"; border.width: 2; border.color: anim.who; rotation: -8
        opacity: anim.scan > 0 ? 0.9 : 0
        Lbl { anchors.centerIn: parent; text: T.signSigned; color: anim.who; size: Theme.caption; strong: true }
    }
    // the magnifier
    Item {
        x: 10 + anim.scan * 110; y: 30 + (anim.scan > 0.5 ? 88 : 0)
        width: 34; height: 34
        opacity: anim.scan > 0 && anim.scan < 1 ? 1 : 0
        Behavior on y { NumberAnimation { duration: Theme.moveBase } }
        Icon { name: "search"; width: 34; height: 34 }
    }
    Chip { x: 162; y: 44; mark: "ok"; text: T.signMatches; opacity: anim.scan > 0.45 ? 1 : 0; Behavior on opacity { NumberAnimation { duration: Theme.base } } }
    Chip { x: 162; y: 130; mark: "fail"; text: T.signNoMatch; opacity: anim.verdict ? 1 : 0; Behavior on opacity { NumberAnimation { duration: Theme.base } } }
}
