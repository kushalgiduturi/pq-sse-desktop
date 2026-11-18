// Stage: Alice on the left, the Cloud in the middle (further away, smaller), the doctors
// on the right. Real events make objects travel between them. The lens chooses whose
// eyes you look through; every zone then shows only what that party can really see.
// Quiet glass: the zones are flat areas of the page panel. The zone that acted last gets a
// soft tint; characters are neutral (a glyph and a name), only real status is colored.
import QtQuick

Item {
    id: stage
    property bool active: false
    property int lens: 0                    // 0 everyone, 1 Alice, 2 first doctor, 3 cloud
    property string lit: ""                 // the zone that acted last
    onLensChanged: if (lens === 3) app.noteCloudView()
    signal inspect(int index)

    readonly property var owner: app.state.owner
    readonly property var cloud: app.state.cloud
    readonly property var doctors: app.state.receivers
    readonly property string lensDoctor: doctors.length > 0 ? doctors[0].name : "receiver-a"
    readonly property var lensNotes: [T.lensNoteEveryone, T.lensNoteAlice, Theme.fmt(T.lensNoteDoctor, { who: cap(lensDoctor) }), T.lensNoteCloud]
    function cap(s) { void app.teachingNames; return app.displayName(s) }   // reading teachingNames re-runs bindings when it changes
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
        width: Math.min(560, parent.width - 40)
        name: T.lensName
        labels: [T.lensEveryone, T.lensAlice, Theme.fmt(T.lensDoctorSees, { who: stage.cap(stage.lensDoctor) }), T.lensCloud]
        current: stage.lens
        onChosen: (i) => stage.lens = i
    }
    Txt { id: lensNote; anchors.top: lensControl.bottom; anchors.topMargin: Theme.sp2; anchors.horizontalCenter: parent.horizontalCenter
          text: stage.lensNotes[stage.lens]; tone: "secondary"; kind: "sm"; width: parent.width - 40; horizontalAlignment: Text.AlignHCenter }

    component Hidden: Column {
        property string who: ""
        width: parent.width; spacing: Theme.sp2
        Repeater { model: 4; Rectangle { required property int index; width: parent.width * [0.9, 0.7, 0.8, 0.5][index]; height: 8; radius: 4; color: Theme.press } }
        Txt { width: parent.width; tone: "tertiary"; kind: "sm"; text: Theme.fmt(T.notVisible, { who: who }) }
    }
    component Zone: Glass {
        id: zone
        property string name: ""
        property string label: ""
        property string sub: ""
        default property alias inside: zoneBody.data
        padding: Theme.sp4
        opacity: stage.lit !== "" && stage.lit !== name && stage.lit !== "security" ? 0.6 : 1
        Behavior on opacity { NumberAnimation { duration: Theme.dur3 } }
        Rectangle {                         // the zone that acted last: a soft tint, no colored rim
            parent: zone
            z: -1
            anchors.fill: parent
            radius: Theme.rCard
            color: stage.lit === zone.name ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.dur3 } }
        }
        Accessible.role: Accessible.Grouping
        Accessible.name: label + ". " + sub
        Row { id: zoneHead; spacing: Theme.sp3
              Avatar { who: zone.name; size: 44; anchors.verticalCenter: parent.verticalCenter }
              Column { width: zone.width - 2 * zone.padding - 56; anchors.verticalCenter: parent.verticalCenter
                       Txt { text: zone.label; kind: "lg"; width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                       Txt { text: zone.sub; tone: "secondary"; kind: "sm"; width: parent.width; lineHeight: 1.35 } } }
        Flickable {
            anchors.top: zoneHead.bottom; anchors.topMargin: Theme.sp4
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            contentHeight: zoneBody.implicitHeight; clip: true
            Column { id: zoneBody; width: parent.width; spacing: Theme.sp2 }
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
            Hidden { visible: stage.hiddenFrom("alice"); who: stage.lens === 3 ? T.theCloud : stage.cap(stage.lensDoctor) }
            Txt { visible: !stage.hiddenFrom("alice") && !stage.owner.open; width: parent.width; text: T.stageNoOwner; tone: "secondary"; kind: "sm" }
            Repeater {
                model: stage.hiddenFrom("alice") ? [] : stage.owner.groups
                Column {
                    id: groupBox
                    required property var modelData
                    width: parent.width; spacing: 0
                    Txt { width: groupBox.width; text: Theme.fmt(T.stageGroup, { g: groupBox.modelData.name, n: groupBox.modelData.docs.length, e: groupBox.modelData.epoch })
                          kind: "sm"; strong: true; elide: Text.ElideRight; wrapMode: Text.NoWrap; bottomPadding: Theme.sp1 }
                    Repeater {
                        model: groupBox.modelData.docs.slice(0, 4)
                        Item {
                            required property var modelData
                            width: groupBox.width; height: docTitle.implicitHeight + 14
                            Icon { id: docIcon; name: "document"; size: 16; color: Theme.text3; anchors.verticalCenter: parent.verticalCenter }
                            Txt { id: docTitle; x: 24; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData.title
                                  kind: "sm"; maximumLineCount: 1; elide: Text.ElideRight; wrapMode: Text.NoWrap; lineHeight: 1.2 }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
                        }
                    }
                    Txt { visible: groupBox.modelData.docs.length > 4; text: Theme.fmt(T.stageMore, { n: groupBox.modelData.docs.length - 4 }); tone: "tertiary"; kind: "sm"; topPadding: Theme.sp1 }
                    Item { width: 1; height: Theme.sp3 }
                }
            }
            Txt { visible: !stage.hiddenFrom("alice") && stage.owner.open; width: parent.width; text: T.keyPicture; tone: "tertiary"; kind: "sm" }
        }

        Zone {
            id: cloudZone
            name: "cloud"; label: T.stageTitleCloud; sub: T.stageSubCloud
            x: aliceZone.width + field.lane
            width: field.width - 2 * field.side - 2 * field.lane
            y: parent.height * 0.07; height: parent.height * 0.84
            Txt { visible: !stage.cloud.running; width: parent.width; text: T.stageNoCloud; tone: "secondary"; kind: "sm" }
            Txt { visible: stage.cloud.running && stage.cloud.docs === 0; width: parent.width; text: T.stageCloudEmpty; tone: "secondary"; kind: "sm" }
            Txt { visible: stage.cloud.docs > 0; width: parent.width; text: Theme.fmt(T.stageStored, { docs: stage.cloud.docs, entries: stage.cloud.entries }); kind: "sm"; strong: true; bottomPadding: Theme.sp1 }
            Repeater {
                model: stage.cloud.storedDocs
                Txt { required property var modelData; width: parent.width; text: modelData.hex.substr(0, 44).replace(/(..)/g, "$1 "); kind: "mono"; tone: "tertiary"; maximumLineCount: 1; wrapMode: Text.NoWrap; elide: Text.ElideRight; lineHeight: 1.6 }
            }
            Txt { visible: stage.cloud.docs > 0; width: parent.width; text: Theme.fmt(T.stageRealBytes, { n: stage.cloud.requests }); tone: "tertiary"; kind: "sm"; topPadding: Theme.sp1 }
        }

        Column {
            x: field.width - field.side
            width: field.side
            height: parent.height
            spacing: Theme.s12
            Txt { visible: stage.doctors.length === 0; width: parent.width; text: T.stageNoDoctors; tone: "secondary"; kind: "sm" }
            Repeater {
                id: doctorRepeater
                model: stage.doctors.slice(0, 3)
                Zone {
                    id: docZone
                    required property var modelData
                    name: modelData.name; label: modelData.display
                    sub: T.stageSubDoctor + (modelData.joined ? Theme.fmt(T.doctorMaySearch, { groups: modelData.groups.join(", ") }) : T.doctorNotJoined)
                    width: field.side
                    height: (field.height - (Math.min(3, stage.doctors.length) - 1) * Theme.s12) / Math.max(1, Math.min(3, stage.doctors.length))
                    Hidden { visible: stage.lens === 2 && stage.hiddenFrom(docZone.name); who: stage.cap(stage.lensDoctor) }
                    Txt { visible: stage.lens === 3 || stage.lens === 1; width: parent.width; tone: "tertiary"; kind: "sm"
                          text: stage.lens === 3 ? T.stageCloudKnows : T.stageAliceKnows }
                    Chip { maxWidth: parent.width; visible: (stage.lens === 0 || (stage.lens === 2 && !stage.hiddenFrom(docZone.name))) && docZone.modelData.result.keyword !== undefined && docZone.modelData.result.keyword !== ""
                           text: Theme.fmt(T.stageMatches, { w: docZone.modelData.result.keyword, n: docZone.modelData.result.hits ? docZone.modelData.result.hits.length : 0 }); mark: "ok" }
                    Txt { visible: (stage.lens === 0 || (stage.lens === 2 && !stage.hiddenFrom(docZone.name))) && docZone.modelData.opened.title !== undefined
                          width: parent.width; kind: "sm"; text: Theme.fmt(T.stageOpened, { title: docZone.modelData.opened.title || "" }) }
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
            width: label.implicitWidth + 28; height: 30; radius: height / 2
            color: Theme.text                 // neutral: the label says what moves
            Txt { id: label; anchors.centerIn: parent; text: packet.record ? packet.record.packet.label : ""; color: Theme.onRole; kind: "sm"; strong: true; wrapMode: Text.NoWrap; lineHeight: 1.0 }
            SequentialAnimation {
                running: true
                NumberAnimation { target: packet; property: "opacity"; from: 0; to: 1; duration: Theme.fast }
                NumberAnimation { target: packet; property: "t"; from: Theme.reduceMotion ? 1 : 0; to: 1; duration: Theme.reduceMotion ? 1 : Theme.stage * 2; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve }
                PauseAnimation { duration: 700 }
                NumberAnimation { target: packet; property: "opacity"; to: 0; duration: Theme.dur2 }
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
        height: 72 * Math.max(1, Theme.scale)
        Rectangle { parent: bottomBar; anchors.top: parent.top; width: parent.width; height: 1; color: Theme.hair }
        SessionTimeline {
            anchors.left: parent.left; anchors.right: playButton.left; anchors.rightMargin: Theme.s16
            anchors.bottom: parent.bottom
            current: events.count - 1
            onChosen: (i) => stage.inspect(i)
        }
        PButton {
            id: playButton
            anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: 6
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
