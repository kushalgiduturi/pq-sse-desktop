// Revoke: the group's key changes. The old key turns grey, a new key goes only to the
// doctors who stay, the revoked doctor's pass dims and a search bounces off. Below, the
// honest difference between the two policies for documents stored before the change.
// Names, groups and the policy come from the recorded event.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property var facts: record ? record.facts : ({})
    readonly property string revoked: record ? record.who : ""
    readonly property var remaining: facts.remaining ? String(facts.remaining).split(", ").filter(function (n) { return n.length > 0 && n !== "none" }) : []
    readonly property bool thorough: String(facts.policy) === "RE"
    readonly property bool turned: progress > 0.20
    readonly property real send: Math.max(0, Math.min(1, (progress - 0.30) / 0.35))
    readonly property bool bounced: progress > 0.68
    readonly property bool compared: progress > 0.82

    component Key: Item {
        property color tone: Theme.warn
        property string label: ""
        width: 46; height: 22
        Rectangle { width: 18; height: 18; radius: 9; anchors.verticalCenter: parent.verticalCenter; color: "transparent"; border.width: 4; border.color: parent.tone }
        Rectangle { x: 16; width: 28; height: 5; anchors.verticalCenter: parent.verticalCenter; color: parent.tone }
        Rectangle { x: 36; y: 13; width: 4; height: 7; color: parent.tone }
        Lbl { y: 22; text: parent.label; size: Theme.caption * 0.9; tone: "secondary"; wrapMode: Text.NoWrap }
    }

    // Alice and the keys of the group
    Avatar { who: T.stageTitleAlice; size: 36; x: 0; y: 6 }
    Key { x: 46; y: 4; tone: anim.turned ? Theme.textMuted : Theme.warn; label: T.revOldKey
          opacity: anim.turned ? 0.6 : 1; Behavior on opacity { NumberAnimation { duration: Theme.base } } }
    Key { x: 46; y: 44; tone: Theme.ok; label: T.revNewKey; visible: anim.turned }

    // the doctors who stay receive the new key; the revoked one does not
    Column {
        x: parent.width * 0.55
        y: 0
        spacing: 10
        Repeater {
            model: anim.remaining.length > 0 && anim.remaining[0] !== "none" ? anim.remaining : [T.revNobodyElse]
            Row {
                required property string modelData
                spacing: 8
                Avatar { visible: modelData !== T.revNobodyElse; who: modelData; size: 28 }
                Lbl { text: modelData; size: Theme.caption; anchors.verticalCenter: parent.verticalCenter }
                Row { visible: anim.send >= 1 && anim.remaining.length > 0; spacing: 4; anchors.verticalCenter: parent.verticalCenter
                      StatusMark { state: "ok"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                      Lbl { text: T.revGotKey; color: Theme.ok; size: Theme.caption } }
            }
        }
        Row {
            spacing: 8
            opacity: anim.turned ? 0.45 : 1
            Behavior on opacity { NumberAnimation { duration: Theme.base } }
            Avatar { who: anim.revoked; size: 28 }
            Lbl { text: anim.revoked; size: Theme.caption; anchors.verticalCenter: parent.verticalCenter }
            Row { visible: anim.bounced; spacing: 4; anchors.verticalCenter: parent.verticalCenter
                  StatusMark { state: "bad"; size: 14; anchors.verticalCenter: parent.verticalCenter }
                  Lbl { text: T.revRefused; color: Theme.bad; size: Theme.caption; strong: true } }
        }
    }
    // the new key travelling (only to those who stay)
    Key {
        visible: anim.send > 0 && anim.send < 1 && anim.remaining.length > 0
        tone: Theme.ok
        x: 96 + (anim.width * 0.55 - 140) * (Theme.reduceMotion ? 1 : anim.send)
        y: 44 - Math.sin(anim.send * Math.PI) * (Theme.reduceMotion ? 0 : 24)
    }

    // R versus RE for documents stored before the change
    Row {
        anchors.bottom: caption.top; anchors.bottomMargin: 8
        spacing: 10
        opacity: anim.compared ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Chip { mark: anim.thorough ? "ok" : "fail"; text: anim.thorough ? T.revOldReLocked : T.revOldStillOld }
        Chip { mark: "ok"; text: T.labNewLocked }
    }
    Lbl {
        id: caption
        anchors.bottom: parent.bottom; width: parent.width
        size: Theme.caption; tone: "secondary"
        text: anim.compared ? (anim.thorough ? T.revCaptionRE : T.revCaptionR)
            : anim.bounced ? Theme.fmt(T.revCaptionBounce, { who: anim.revoked })
            : anim.turned ? T.revCaptionSend : T.revCaptionStart
    }
}
