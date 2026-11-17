// Key exchange (ML-KEM): the receiver's public key is an open lock, the sender seals a
// fresh secret in a capsule, the capsule flies across, the private key opens it, and both
// sides hold the same secret (matching glow, never the value).
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property string receiver: record ? (record.kind === "revoke" ? T.kemOthers : record.who) : ""
    readonly property real fly: Math.max(0, Math.min(1, (progress - 0.30) / 0.40))
    readonly property bool sealed: progress > 0.22
    readonly property bool opened: progress > 0.78

    Avatar { id: left; who: T.stageTitleAlice; size: 40; x: 6; y: 30 }
    Avatar { id: right; who: anim.receiver; size: 40; x: parent.width - 46; y: 30
             color: anim.record && anim.record.kind === "revoke" ? Theme.bob : Theme.roleColor(anim.receiver) }
    Lbl { x: 0; y: 74; text: T.stageTitleAlice; size: Theme.caption; tone: "secondary" }
    Lbl { anchors.right: parent.right; y: 74; text: anim.receiver; size: Theme.caption; tone: "secondary" }

    // public key: an open lock next to the receiver
    Item {
        x: parent.width - 96; y: 34; width: 30; height: 34
        opacity: anim.progress > 0.04 ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Rectangle { x: 13; y: anim.opened ? 0 : -4; width: 14; height: 16; radius: 7; color: "transparent"; border.width: 3; border.color: Theme.roleColor(anim.receiver) }
        Rectangle { x: 2; y: 13; width: 24; height: 19; radius: 5; color: Theme.roleColor(anim.receiver) }
    }
    // the capsule
    Rectangle {
        id: capsule
        width: 54; height: 26; radius: 13
        x: 58 + (parent.width - 220) * (Theme.reduceMotion ? (anim.fly > 0.5 ? 1 : 0) : anim.fly)
        y: 38 - Math.sin(anim.fly * Math.PI) * (Theme.reduceMotion ? 0 : 16)
        color: Theme.tint(Theme.warn, anim.opened ? 0.25 : 0.95)
        border.width: 2; border.color: Theme.warn
        opacity: anim.sealed ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Lbl { anchors.centerIn: parent; text: anim.opened ? T.kemOpen : T.kemSealed; size: Theme.caption; strong: true; color: anim.opened ? Theme.textPrimary : Theme.accentOn }
    }
    // the same secret on both sides: matching glow
    Repeater {
        model: 2
        Rectangle {
            required property int index
            x: index === 0 ? 0 : anim.width - 52
            y: 24; width: 52; height: 52; radius: 26
            color: "transparent"; border.width: 3; border.color: Theme.ok
            opacity: anim.opened ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.slow } }
        }
    }
    Row {
        y: 100; spacing: 6
        Chip { text: T.kemName }
        Chip { text: T.kemSafe }
        Chip { visible: anim.record && anim.record.facts.cap_bytes !== undefined; text: Theme.fmt(T.kemBytes, { n: anim.record ? anim.record.facts.cap_bytes : "" }) }
    }
    Lbl {
        anchors.bottom: parent.bottom; width: parent.width
        size: Theme.caption; tone: "muted"
        text: anim.opened ? T.kemOpened : anim.sealed ? T.kemSealing : T.kemPublic
    }
}
