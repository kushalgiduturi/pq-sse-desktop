// Stage: Alice on the left, the Cloud in the middle (further away, smaller), the doctors
// on the right. Real events make objects travel between them. The lens chooses whose
// eyes you look through; every zone then shows only what that party can really see.
import QtQuick

Item {
    id: stage
    property bool active: false
    property int lens: 0                    // 0 everyone, 1 Alice, 2 first doctor, 3 cloud
    property string lit: ""                 // the zone that acted last
    signal inspect(int index)

    readonly property var owner: app.state.owner
    readonly property var cloud: app.state.cloud
    readonly property var doctors: app.state.receivers
    readonly property string lensDoctor: doctors.length > 0 ? doctors[0].name : "bob"
    readonly property var lensNotes: [T.lensNoteEveryone, T.lensNoteAlice, T.lensNoteBob.replace(/Bob/g, cap(lensDoctor)).replace(/his/g, "their").replace(/him/g, "them"), T.lensNoteCloud]
    function cap(s) { return s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s }
    function hiddenFrom(zone) {             // zone: "alice", "cloud" or a doctor's name
        if (lens === 0) return false
        if (lens === 1) return false
        if (lens === 2) return zone === "alice" || (zone !== "cloud" && zone !== lensDoctor)
        return zone !== "cloud"
    }
    function zoneItem(name) {
        var key = String(name).toLowerCase()
        if (key === "alice") return aliceZone
        if (key === "cloud") return cloudZone
        for (var i = 0; i < doctorRepeater.count; i++) {
            var item = doctorRepeater.itemAt(i)
            if (item && item.name === key) return item
        }
        return doctorRepeater.count > 0 ? doctorRepeater.itemAt(0) : cloudZone
    }
    function fly(record) {
        if (!record.packet || record.scope === "practice") return
        var from = zoneItem(record.packet.src === "receiver" ? record.who : record.packet.src)
        var to = zoneItem(record.packet.dst === "receiver" ? record.who : record.packet.dst)
        var a = from.mapToItem(stage, from.width / 2, from.height / 2)
        var b = to.mapToItem(stage, to.width / 2, to.height / 2)
        packetComponent.createObject(packetLayer, { fromX: a.x, fromY: a.y, toX: b.x, toY: b.y, record: record })
    }
    Connections {
        target: events
        function onAdded(record) {
            if (record.scope === "practice") return
            stage.lit = record.tag === "receiver" ? record.who.toLowerCase() : record.tag
            litTimer.restart()
            if (stage.active) stage.fly(record)
        }
    }
    Timer { id: litTimer; interval: 2200; onTriggered: stage.lit = "" }

    // ---------------------------------------------------------------- lens
    Segmented {
        id: lensControl
        anchors.horizontalCenter: parent.horizontalCenter
        width: Math.min(620, parent.width - 40)
        name: "Whose view"
        labels: [T.lensEveryone, T.lensAlice, stage.cap(stage.lensDoctor) + " sees", T.lensCloud]
        current: stage.lens
        onChosen: (i) => stage.lens = i
    }
    Lbl { id: lensNote; anchors.top: lensControl.bottom; anchors.topMargin: 6; anchors.horizontalCenter: parent.horizontalCenter
          text: stage.lensNotes[stage.lens]; tone: "secondary"; size: Theme.caption; width: parent.width - 40; horizontalAlignment: Text.AlignHCenter }

    component Hidden: Column {
        property string who: ""
        width: parent.width; spacing: 6
        Repeater { model: 4; Rectangle { required property int index; width: parent.width * [0.9, 0.7, 0.8, 0.5][index]; height: 10; radius: 5; color: Theme.tint(Theme.textMuted, 0.35) } }
        Lbl { width: parent.width; tone: "muted"; size: Theme.caption; text: "Not visible to " + who + "." }
    }
    component Zone: Glass {
        id: zone
        property string name: ""
        property string label: ""
        property string sub: ""
        default property alias inside: zoneBody.data
        radius: Theme.rPanel
        padding: Theme.s16
        rim: stage.lit === name ? Theme.roleColor(name) : Theme.glassStroke
        rimWidth: stage.lit === name ? 3 : 1
        opacity: stage.lit !== "" && stage.lit !== name && stage.lit !== "security" ? 0.72 : 1
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
        Accessible.role: Accessible.Grouping
        Accessible.name: label + ". " + sub
        Row { id: zoneHead; spacing: 12
              Avatar { who: zone.label; size: 44; color: Theme.roleColor(zone.name) }
              Column { Lbl { text: zone.label; size: Theme.title; strong: true } Lbl { text: zone.sub; tone: "secondary"; size: Theme.caption } } }
        Flickable {
            anchors.top: zoneHead.bottom; anchors.topMargin: 12
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            contentHeight: zoneBody.implicitHeight; clip: true
            Column { id: zoneBody; width: parent.width; spacing: 8 }
        }
    }

    Item {
        id: field
        anchors.top: lensNote.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: bottomBar.top; anchors.bottomMargin: Theme.s16
        width: parent.width
        readonly property real lane: Math.max(60, width * 0.06)
        readonly property real side: (width - 2 * lane) * 0.34

        Zone {
            id: aliceZone
            name: "alice"; label: T.stageTitleAlice; sub: T.stageSubAlice
            width: field.side; height: parent.height
            Hidden { visible: stage.hiddenFrom("alice"); who: stage.lens === 3 ? "the cloud" : stage.cap(stage.lensDoctor) }
            Lbl { visible: !stage.hiddenFrom("alice") && !stage.owner.open; width: parent.width; text: T.stageNoOwner; tone: "secondary" }
            Repeater {
                model: stage.hiddenFrom("alice") ? [] : stage.owner.groups
                Column {
                    id: groupBox
                    required property var modelData
                    width: parent.width; spacing: 4
                    Chip { maxWidth: groupBox.width; text: modelData.name + ": " + modelData.docs.length + " documents, key period " + modelData.epoch; mark: "dot"; dot: Theme.alice }
                    Repeater {
                        model: groupBox.modelData.docs.slice(0, 4)
                        Rectangle {
                            required property var modelData
                            width: groupBox.width; height: docTitle.implicitHeight + 12; radius: 8
                            color: Theme.tint(Theme.glassRaised, 0.9); border.width: 1; border.color: Theme.tint(Theme.alice, 0.6)
                            Lbl { id: docTitle; x: 10; width: parent.width - 20; anchors.verticalCenter: parent.verticalCenter; text: modelData.title; size: Theme.caption; maximumLineCount: 1; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                        }
                    }
                    Lbl { visible: groupBox.modelData.docs.length > 4; text: "and " + (groupBox.modelData.docs.length - 4) + " more"; tone: "muted"; size: Theme.caption }
                }
            }
            Lbl { visible: !stage.hiddenFrom("alice") && stage.owner.open; width: parent.width; text: T.keyPicture; tone: "muted"; size: Theme.caption }
        }

        Zone {
            id: cloudZone
            name: "cloud"; label: T.stageTitleCloud; sub: T.stageSubCloud
            x: aliceZone.width + field.lane
            width: field.width - 2 * field.side - 2 * field.lane
            y: parent.height * 0.07; height: parent.height * 0.84
            scale: Theme.reduceMotion ? 1 : 0.97
            Lbl { visible: !stage.cloud.running; width: parent.width; text: T.stageNoCloud; tone: "secondary" }
            Lbl { visible: stage.cloud.running && stage.cloud.docs === 0; width: parent.width; text: T.stageCloudEmpty; tone: "secondary" }
            Chip { maxWidth: parent.width; visible: stage.cloud.docs > 0; text: stage.cloud.docs + " locked documents, " + stage.cloud.entries + " index entries"; mark: "dot"; dot: Theme.cloud }
            Repeater {
                model: stage.cloud.storedDocs
                Lbl { required property var modelData; width: parent.width; text: modelData.hex.substr(0, 44).replace(/(..)/g, "$1 "); font.family: Theme.monoFamily; size: Theme.caption; tone: "muted"; maximumLineCount: 1; wrapMode: Text.NoWrap; elide: Text.ElideRight }
            }
            Lbl { visible: stage.cloud.docs > 0; width: parent.width; text: "These are the real stored bytes. " + stage.cloud.requests + " requests so far."; tone: "muted"; size: Theme.caption }
        }

        Column {
            x: field.width - field.side
            width: field.side
            height: parent.height
            spacing: Theme.s12
            Lbl { visible: stage.doctors.length === 0; width: parent.width; text: T.stageNoDoctors; tone: "secondary" }
            Repeater {
                id: doctorRepeater
                model: stage.doctors.slice(0, 3)
                Zone {
                    id: docZone
                    required property var modelData
                    name: modelData.name; label: modelData.display
                    sub: T.stageSubDoctor + (modelData.joined ? ". May search: " + modelData.groups.join(", ") : ". Has not joined yet.")
                    width: field.side
                    height: (field.height - (Math.min(3, stage.doctors.length) - 1) * Theme.s12) / Math.max(1, Math.min(3, stage.doctors.length))
                    Hidden { visible: stage.lens === 2 && stage.hiddenFrom(docZone.name); who: stage.cap(stage.lensDoctor) }
                    Lbl { visible: stage.lens === 3 || stage.lens === 1; width: parent.width; tone: "muted"; size: Theme.caption
                          text: stage.lens === 3 ? "The cloud knows this pass and its groups. It does not know what was searched." : "Alice knows whom she approved. She does not see searches." }
                    Chip { maxWidth: parent.width; visible: (stage.lens === 0 || (stage.lens === 2 && !stage.hiddenFrom(docZone.name))) && docZone.modelData.result.keyword !== undefined && docZone.modelData.result.keyword !== ""
                           text: "'" + docZone.modelData.result.keyword + "': " + (docZone.modelData.result.hits ? docZone.modelData.result.hits.length : 0) + " matches, checks passed"; mark: "ok" }
                    Lbl { visible: (stage.lens === 0 || (stage.lens === 2 && !stage.hiddenFrom(docZone.name))) && docZone.modelData.opened.title !== undefined
                          width: parent.width; size: Theme.caption; text: "Opened: " + (docZone.modelData.opened.title || "") }
                }
            }
        }
        Item { id: packetLayer; anchors.fill: parent; z: 5 }
    }

    Component {
        id: packetComponent
        Rectangle {
            id: packet
            property real fromX: 0; property real fromY: 0; property real toX: 0; property real toY: 0
            property var record: null
            property real t: 0
            x: fromX + (toX - fromX) * t - width / 2
            y: fromY + (toY - fromY) * t - height / 2 - field.y - Math.sin(t * Math.PI) * (Theme.reduceMotion ? 0 : 40)
            width: label.implicitWidth + 22; height: 34; radius: 10
            color: record ? Theme.roleColor(record.packet.src === "receiver" ? record.who : record.packet.src) : Theme.accent
            border.width: 1; border.color: Theme.textPrimary
            Lbl { id: label; anchors.centerIn: parent; text: packet.record ? packet.record.packet.label : ""; color: Theme.onRole; size: Theme.caption; strong: true }
            SequentialAnimation {
                running: true
                NumberAnimation { target: packet; property: "opacity"; from: 0; to: 1; duration: Theme.fast }
                NumberAnimation { target: packet; property: "t"; from: Theme.reduceMotion ? 1 : 0; to: 1; duration: Theme.reduceMotion ? 1 : Theme.stage * 2; easing.type: Easing.InOutCubic }
                PauseAnimation { duration: 700 }
                NumberAnimation { target: packet; property: "opacity"; to: 0; duration: Theme.base }
                ScriptAction { script: packet.destroy() }
            }
            TapHandler { onTapped: stage.inspect(packet.record.index) }
        }
    }

    // ---------------------------------------------------------------- bottom: session timeline and "play"
    Glass {
        id: bottomBar
        anchors.bottom: parent.bottom
        width: parent.width
        height: 84 * Math.max(1, Theme.scale)
        padding: Theme.s12
        SessionTimeline {
            anchors.left: parent.left; anchors.right: playButton.left; anchors.rightMargin: Theme.s16
            anchors.verticalCenter: parent.verticalCenter
            current: events.count - 1
            onChosen: (i) => stage.inspect(i)
        }
        PButton {
            id: playButton
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
            primary: true
            enabled: !app.busy
            text: T.stagePlay
            Accessible.description: T.stagePlayHint
            onClicked: {
                var next = app.lessonStep
                var steps = app.lessonSteps
                while (next < steps.length && (!steps[next].runnable || app.lessonDone.indexOf(steps[next].key) >= 0)) next++
                if (next < steps.length) app.runLessonStep(next)
            }
        }
    }
}
