// Encryption (AES-256-GCM): readable letters flip into ciphertext glyphs as the padlock
// passes, then the index entries line up into a chain, then Alice's stamp lands.
// For Decrypt the record has reverse = true and the letters go the other way.
// The readable line is a real document title of the group, the glyphs are the real stored
// ciphertext as the cloud holds it. The key is never part of the record.
import QtQuick

Item {
    id: anim
    property var record: null
    property real progress: 0
    readonly property bool reverse: record ? record.reverse : false
    readonly property real lockPhase: reverse ? 0.9 : 0.25
    readonly property real p1: Math.max(0, Math.min(1, progress / lockPhase))
    readonly property real p2: reverse ? 0 : Math.max(0, Math.min(1, (progress - 0.27) / 0.45))
    readonly property real p3: reverse ? 0 : Math.max(0, Math.min(1, (progress - 0.76) / 0.16))
    readonly property string plain: {
        var facts = record ? record.facts : {}
        var groups = app.state.owner ? app.state.owner.groups : []
        for (var i = 0; i < groups.length; i++)
            if (groups[i].name === facts.g && groups[i].docs.length > 0) return groups[i].docs[groups[i].docs.length - 1].title
        return Theme.fmt(T.encDocument, { g: facts.g || "the group" })
    }
    readonly property string cipher: {
        var stored = app.state.cloud ? app.state.cloud.storedDocs : []
        return stored.length > 0 ? stored[0].hex : "9f3ac107e25b88d41c6ea0f342b70d913cee57a908f16b2d"
    }
    readonly property bool realCipher: app.state.cloud && app.state.cloud.storedDocs.length > 0
    readonly property int shownLetters: Math.min(24, plain.length)
    readonly property real cell: Math.min(22, (width - 60) / Math.max(1, shownLetters))
    readonly property int entries: record && record.facts.entries ? Math.min(14, parseInt(record.facts.entries) || 0) : 0
    // Did the GPU really do this batch? "GPU" yes, "CPU" no, "Auto (GPU from N messages, else CPU)"
    // only when the real number of entries reached N.
    readonly property bool gpu: {
        var engine = record ? String(record.facts.engine || "") : ""
        var real = record ? (parseInt(record.facts.entries) || 0) : 0
        var auto = engine.match(/GPU from (\d+)/)
        if (auto) return real >= parseInt(auto[1])
        return engine.indexOf("GPU") === 0
    }

    Row {
        id: letters
        y: 6
        Repeater {
            model: anim.shownLetters
            Item {
                id: letter
                required property int index
                readonly property real raw: Math.max(0, Math.min(1, anim.p1 * (anim.shownLetters + 3) - index))
                readonly property real p: anim.reverse ? 1 - raw : raw
                width: anim.cell; height: 34
                Rectangle {
                    anchors.fill: parent; anchors.margins: 1; radius: 6
                    color: letter.p > 0.5 ? Theme.tint(Theme.accent, 0.22) : Theme.hover
                    border.width: 1; border.color: letter.p > 0.5 ? Theme.accent : Theme.hairStrong
                }
                Text {
                    anchors.centerIn: parent
                    text: letter.p > 0.5 ? anim.cipher.charAt(letter.index % anim.cipher.length) : anim.plain.charAt(letter.index)
                    color: letter.p > 0.5 ? Theme.accent : Theme.textPrimary
                    font.family: letter.p > 0.5 ? Theme.monoFamily : Theme.fontFamily
                    font.pixelSize: Math.min(16, anim.cell * 0.72)
                    opacity: Theme.reduceMotion ? 1 : 1 - Math.sin(letter.raw * Math.PI) * 0.75
                    transform: Rotation {
                        origin.x: 4; origin.y: 10
                        axis { x: 1; y: 0; z: 0 }
                        angle: Theme.reduceMotion ? 0 : Math.sin(letter.raw * Math.PI) * 80
                    }
                }
            }
        }
    }
    // The padlock: a picture for AES-256-GCM (the inspector says so in words).
    Item {
        width: 30; height: 38
        x: Math.min(letters.width + 4, anim.p1 * (anim.shownLetters + 3) * anim.cell - 6)
        y: 2
        Rectangle { x: 7; y: anim.p1 >= 1 && !anim.reverse ? 5 : 0; width: 16; height: 18; radius: 8; color: "transparent"; border.width: 3; border.color: Theme.text
                    Behavior on y { NumberAnimation { duration: Theme.moveBase; easing.type: Easing.OutBack } } }
        Rectangle { x: 2; y: 15; width: 26; height: 21; radius: 5; color: Theme.text }
    }
    Row {
        y: 46; spacing: 6
        opacity: anim.p1 >= 1 ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Chip { text: T.encAes }
        Chip { text: T.encNonce }
        Chip { text: T.encTag }
        Chip { visible: anim.record && anim.record.facts.bytes !== undefined; text: Theme.fmt(T.encBytes, { n: anim.record ? anim.record.facts.bytes : "" }) }
    }
    // Index entries: secret addresses that snap into a hash chain. One lane on the CPU,
    // several lanes lighting up together on the GPU.
    Item {
        visible: !anim.reverse && anim.entries > 0
        y: 86; width: parent.width; height: 44
        Repeater {
            model: anim.entries
            Rectangle {
                required property int index
                readonly property real appear: anim.gpu ? (anim.p2 > 0.15 ? 1 : 0) : (anim.p2 * anim.entries > index ? 1 : 0)
                x: index * (parent.width - 8) / anim.entries
                width: (parent.width - 8) / anim.entries - 3; height: 20; radius: 5
                color: Theme.tint(Theme.accent, 0.25); border.width: 1; border.color: Theme.accent
                opacity: appear
                scale: appear ? 1 : 0.6
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                Behavior on scale { enabled: !Theme.reduceMotion; NumberAnimation { duration: Theme.base; easing.type: Easing.OutBack } }
                Rectangle {          // the link to the next entry
                    visible: index < anim.entries - 1
                    x: parent.width; y: 9; width: 3; height: 2; color: Theme.textSecondary
                    opacity: anim.p2 * anim.entries > index + 1 ? 1 : 0
                }
            }
        }
        Lbl {
            y: 24; size: Theme.caption; tone: "muted"
            text: Theme.fmt(anim.gpu ? T.encEntriesGpu : T.encEntriesCpu, { n: anim.record ? anim.record.facts.entries : "" })
            opacity: anim.p2 > 0 ? 1 : 0
        }
    }
    // Alice's stamp on the batch.
    Rectangle {
        visible: !anim.reverse
        anchors.right: parent.right
        y: 128 - (1 - anim.p3) * (Theme.reduceMotion ? 0 : 40)
        width: stampText.implicitWidth + 20; height: 28; radius: 6
        color: "transparent"; border.width: 2; border.color: Theme.alice
        rotation: -6
        opacity: anim.p3
        Lbl { id: stampText; anchors.centerIn: parent; text: T.encStamp; color: Theme.alice; size: Theme.caption; strong: true }
    }
    Lbl {
        anchors.bottom: parent.bottom
        size: Theme.caption; tone: "muted"
        text: anim.realCipher ? T.encReal : T.encSample
    }
}
