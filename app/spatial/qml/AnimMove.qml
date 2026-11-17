// The general picture for steps without a special animation: who sent what to whom.
// Source, destination and label come from the recorded event.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property var packet: record ? record.packet : null
    readonly property string src: packet ? (packet.src === "receiver" ? record.who : packet.src) : (record ? (record.tag === "receiver" ? record.who : record.tag) : "")
    readonly property string dst: packet ? (packet.dst === "receiver" ? record.who : packet.dst) : ""
    readonly property real t: Theme.reduceMotion ? (progress > 0.5 ? 1 : 0) : Math.max(0, Math.min(1, (progress - 0.15) / 0.6))

    Avatar { who: anim.src; size: 42; x: 6; y: 30 }
    Avatar { who: anim.dst; size: 42; x: parent.width - 48; y: 30; visible: anim.dst.length > 0 }
    Lbl { x: 0; y: 78; text: anim.src; size: Theme.caption; tone: "secondary" }
    Lbl { anchors.right: parent.right; y: 78; text: anim.dst; size: Theme.caption; tone: "secondary" }
    Rectangle {
        visible: anim.packet !== null
        x: 60 + anim.t * (anim.width - 190)
        y: 36
        width: tag.implicitWidth + 18; height: 30; radius: 8
        color: Theme.roleColor(anim.src)
        Lbl { id: tag; anchors.centerIn: parent; text: anim.packet ? anim.packet.label : ""; color: Theme.onRole; size: Theme.caption; strong: true }
    }
    Lbl {
        y: 104; width: parent.width
        size: Theme.caption; tone: "secondary"
        text: anim.packet ? Theme.fmt(T.moveInside, { contents: anim.packet.contents, readers: anim.packet.readers })
                          : (anim.record ? anim.record.line : "")
    }
}
