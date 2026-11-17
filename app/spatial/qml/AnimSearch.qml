// Search (TokenGen and Search): the word turns into a sealed slip, the slip flies to the
// cloud, the matching entries glow without the word ever being shown there, and locked
// boxes fly back. Counts are the real ones from the event.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property var facts: record ? record.facts : ({})
    readonly property string keyword: facts.keyword !== undefined ? facts.keyword : ""
    readonly property int hits: Math.max(1, Math.min(6, parseInt(facts.entries !== undefined ? facts.entries : facts.addresses) || 1))
    readonly property real seal: Math.max(0, Math.min(1, progress / 0.25))
    readonly property real fly: Math.max(0, Math.min(1, (progress - 0.25) / 0.25))
    readonly property bool glow: progress > 0.55
    readonly property real back: Math.max(0, Math.min(1, (progress - 0.70) / 0.30))
    readonly property real lane: width - 150
    readonly property var stored: app.state.cloud ? app.state.cloud.storedEntries : []

    Avatar { who: anim.record ? anim.record.who : "Bob"; size: 38; x: 4; y: 32
             color: Theme.roleColor(anim.record && anim.record.tag === "receiver" ? anim.record.who : "bob") }
    Avatar { who: "Cloud"; size: 38; x: parent.width - 132; y: 6 }

    // the word stays on the doctor's side
    Rectangle {
        x: 0; y: 78; width: wordText.implicitWidth + 16; height: 24; radius: 6
        color: Theme.tint(Theme.glassRaised, 0.95); border.width: 1; border.color: Theme.tint(Theme.glassStroke, 0.7)
        visible: anim.keyword.length > 0
        Lbl { id: wordText; anchors.centerIn: parent; text: "'" + anim.keyword + "'"; size: Theme.caption }
    }
    Lbl { x: 0; y: 106; size: Theme.caption; tone: "muted"; text: anim.keyword.length > 0 ? T.searchStays : "" }

    // the slip
    Rectangle {
        x: 50 + (Theme.reduceMotion ? (anim.fly > 0.5 ? 1 : 0) : anim.fly) * (anim.lane - 110)
        y: 36
        width: 58; height: 30; radius: 7
        color: Theme.bob
        opacity: anim.seal > 0.3 && anim.back < 0.05 ? 1 : 0
        scale: 0.7 + 0.3 * anim.seal
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Lbl { anchors.centerIn: parent; text: T.searchSlip; color: Theme.onRole; size: Theme.caption; strong: true }
    }
    // what the cloud stores: cells of scrambled values; the addressed ones glow
    Grid {
        x: parent.width - 132; y: 50
        columns: 4; spacing: 4
        Repeater {
            model: 12
            Rectangle {
                required property int index
                readonly property bool hit: index % 3 === 1 && Math.floor(index / 3) < anim.hits
                width: 28; height: 20; radius: 4
                color: hit && anim.glow ? Theme.tint(Theme.ok, 0.85) : Theme.tint(Theme.glassRaised, 0.95)
                border.width: 1; border.color: hit && anim.glow ? Theme.ok : Theme.tint(Theme.glassStroke, 0.6)
                Behavior on color { ColorAnimation { duration: Theme.base } }
                Lbl { anchors.centerIn: parent; text: anim.stored.length > 0 ? anim.stored[index % anim.stored.length].address.substr((index * 2) % 28, 2) : "··"; size: 10; tone: "muted"; font.family: Theme.monoFamily }
            }
        }
    }
    // locked boxes fly back
    Repeater {
        model: anim.hits
        Rectangle {
            required property int index
            readonly property real t: Theme.reduceMotion ? (anim.back > 0.5 ? 1 : 0) : Math.max(0, Math.min(1, anim.back * 1.4 - index * 0.1))
            x: (anim.width - 170) - t * (anim.width - 230) + index * 3
            y: 100 + index * 4
            width: 22; height: 18; radius: 4
            color: Theme.cloud; border.width: 1; border.color: Theme.textPrimary
            opacity: anim.back > 0 ? 1 : 0
        }
    }
    Lbl {
        anchors.bottom: parent.bottom; width: parent.width
        size: Theme.caption; tone: "muted"
        text: anim.back > 0 ? Theme.fmt(T.searchBack, { n: anim.facts.entries !== undefined ? anim.facts.entries : "the" })
            : anim.glow ? T.searchGlow : anim.fly > 0 ? T.searchFly : T.searchSeal
    }
}
