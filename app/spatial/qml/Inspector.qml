// The Step Inspector: one recorded step at four levels of detail, with a player that
// replays the record. Nothing here is computed in QML: the record comes from Python.
// Quiet glass: a depth-4 drawer on the right; the picture sits in a depth-1 inset.
import QtQuick

Glass {
    id: ins
    property int index: -1
    property var record: index >= 0 && index < events.count ? events.records[index] : null
    property var override: null           // a record that is not in the event log (an attack card)
    readonly property var shown: override !== null ? override : record
    readonly property int stepCount: shown ? shown.steps.length : 0
    property real progress: 0
    property real speed: 1.0
    property bool playing: false
    readonly property int step: stepCount === 0 ? 0 : Math.min(stepCount - 1, Math.floor(progress * stepCount + 0.0001))
    readonly property var speeds: [0.25, 0.5, 1, 2, 4]
    signal close()
    signal jump(int index)

    floating: true
    radius: Theme.rFloat
    padding: Theme.sp6
    Accessible.role: Accessible.Pane
    Accessible.name: T.inspectorOpen

    function play() {
        if (stepCount === 0) return
        if (progress >= 0.999) progress = 0
        playing = true
    }
    function pause() { playing = false }
    function toStep(i) { playing = false; progress = Math.max(0, Math.min(stepCount - 1, i)) / stepCount + 0.001 }
    function replay() { progress = 0; play() }
    onShownChanged: { progress = 0; if (shown && ins.visible) play() }
    onVisibleChanged: if (visible && shown && progress < 0.01) play()

    // The player. With motion: progress runs smoothly. With Reduce motion: it jumps one
    // sub-step at a time, so the visuals are still frames with captions.
    NumberAnimation {
        id: runner
        target: ins; property: "progress"
        running: ins.playing && !Theme.reduceMotion
        from: ins.progress; to: 1
        duration: Math.max(1, (1 - ins.progress) * ins.stepCount * 1700 / ins.speed)
        onFinished: ins.playing = false
    }
    Timer {
        running: ins.playing && Theme.reduceMotion
        interval: 1700 / ins.speed
        repeat: true
        onTriggered: {
            if (ins.step >= ins.stepCount - 1) { ins.progress = 1; ins.playing = false }
            else ins.progress = (ins.step + 1) / ins.stepCount + 0.001
        }
    }

    Empty { visible: ins.shown === null; anchors.centerIn: parent; width: parent.width - 20; icon: "inspect"; title: T.inspectorEmpty }

    Flickable {
        visible: ins.shown !== null
        anchors.fill: parent
        contentHeight: column.implicitHeight
        clip: true
        Column {
            id: column
            width: parent.width
            spacing: Theme.sp4

            Item {
                width: parent.width; height: head.implicitHeight
                Column {
                    id: head
                    width: parent.width - 48
                    spacing: Theme.sp1
                    Row {
                        spacing: Theme.sp3
                        Avatar { who: ins.shown ? (ins.shown.tag === "receiver" ? ins.shown.who : ins.shown.tag) : ""; size: 32; anchors.verticalCenter: parent.verticalCenter }
                        Txt { text: ins.shown ? ins.shown.title : ""; kind: "xl"; width: head.width - 44; anchors.verticalCenter: parent.verticalCenter }
                    }
                    Txt { text: ins.shown ? ins.shown.technical + (ins.shown.scope === "practice" ? T.inspectorPractice : "") : ""; tone: "secondary"; kind: "sm"; width: parent.width }
                }
                Button { anchors.right: parent.right; kind: "ghost"; small: true; icon: "close"; text: ""; minWidth: 36
                         Accessible.name: T.close; onClicked: ins.close() }
            }

            Segmented {
                width: parent.width
                name: T.detailLevel
                labels: width > 430 * Theme.scale ? [T.layerPlain, T.layerMoved, T.layerHood, T.layerSafe]
                                                 : [T.layerPlainShort, T.layerMovedShort, T.layerHoodShort, T.layerSafeShort]
                current: app.detailLevel
                onChosen: (i) => app.setDetailLevel(i)
            }

            // The picture of this step is visible at every level: it is the anchor.
            Item {
                width: parent.width
                height: 190 + (Theme.scale - 1) * 150
                clip: true
                Surface { anchors.fill: parent; depth: 1; radius: Theme.rCard; padding: 0 }
                Loader {
                    anchors.fill: parent; anchors.margins: 12
                    active: ins.shown !== null
                    source: !ins.shown ? "" : ins.shown.kind.indexOf("attack:") === 0 ? "AnimAttack.qml" : ({ encrypt: "AnimEncrypt.qml", kem: "AnimKem.qml", sign: "AnimSign.qml",
                                                 search: "AnimSearch.qml", verify: "AnimVerify.qml",
                                                 update: "AnimUpdate.qml", revoke: "AnimRevoke.qml" })[ins.shown.anim] || "AnimMove.qml"
                    onLoaded: {
                        item.record = Qt.binding(function () { return ins.shown })
                        item.progress = Qt.binding(function () { return ins.progress })
                    }
                }
            }
            Txt { width: parent.width; tone: "tertiary"; kind: "sm"; text: ins.shown ? ins.shown.replayNote : "" }

            Flow {
                width: parent.width
                spacing: Theme.sp2
                Button { small: true; kind: "secondary"; text: T.stepBack; onClicked: ins.toStep(ins.step - 1) }
                Button { small: true; kind: "primary"; icon: ins.playing ? "pause" : "play"; text: ins.playing ? T.pause : T.play; onClicked: ins.playing ? ins.pause() : ins.play() }
                Button { small: true; kind: "secondary"; text: T.stepNext; onClicked: ins.toStep(ins.step + 1) }
                Button { small: true; kind: "ghost"; text: T.replay; onClicked: ins.replay() }
                Button {
                    small: true; kind: "ghost"
                    text: Theme.fmt(T.speedX, { n: ins.speed })
                    Accessible.name: T.speed + " " + ins.speed
                    onClicked: ins.speed = ins.speeds[(ins.speeds.indexOf(ins.speed) + 1) % ins.speeds.length]
                }
            }
            Item {               // scrubber of this step: an inset track and the played part in accent
                width: parent.width; height: 6
                Surface { anchors.fill: parent; depth: 1; radius: 3; padding: 0 }
                Rectangle { width: parent.width * ins.progress; height: 6; radius: 3; color: Theme.accent }
                MouseArea {
                    anchors.fill: parent; anchors.margins: -8
                    onPressed: (m) => { ins.playing = false; ins.progress = Math.max(0, Math.min(1, m.x / width)) }
                    onPositionChanged: (m) => { if (pressed) ins.progress = Math.max(0, Math.min(1, m.x / width)) }
                }
            }

            // Layer 1: plain words
            Column {
                visible: app.detailLevel === 0
                width: parent.width; spacing: Theme.sp2
                Txt { width: parent.width; text: ins.shown ? ins.shown.line : ""; kind: "lg" }
                Txt { width: parent.width; text: ins.shown ? ins.shown.more : ""; tone: "secondary" }
            }
            // Layer 2: what moved, as a numbered timeline
            Column {
                visible: app.detailLevel === 1
                width: parent.width; spacing: 0
                Repeater {
                    model: ins.shown ? ins.shown.steps : []
                    Item {
                        id: stepRow
                        required property string modelData
                        required property int index
                        width: column.width
                        height: Math.max(Theme.touch ? 44 : 32, stepText.implicitHeight + 12)
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: Theme.fmt(T.stepN, { n: index + 1, text: modelData })
                        Keys.onReturnPressed: ins.toStep(index)
                        Rectangle {
                            anchors.fill: parent; anchors.leftMargin: -Theme.sp2; anchors.rightMargin: -Theme.sp2
                            radius: Theme.rSm
                            color: stepRow.index === ins.step ? Theme.hover : "transparent"
                            border.width: stepRow.activeFocus ? 2 : 0; border.color: Theme.ring
                        }
                        Icon {          // done: a check; now: a chevron; later: nothing
                            visible: stepRow.index <= ins.step
                            anchors.verticalCenter: parent.verticalCenter
                            name: stepRow.index < ins.step ? "check" : "chevron"
                            size: 16
                            color: stepRow.index < ins.step ? Theme.text3 : Theme.text
                        }
                        Txt {
                            id: stepText
                            x: 28; width: parent.width - 28
                            anchors.verticalCenter: parent.verticalCenter
                            text: stepRow.modelData
                            tone: stepRow.index === ins.step ? "primary" : "secondary"
                            strong: stepRow.index === ins.step
                        }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: ins.toStep(stepRow.index) }
                    }
                }
            }
            // Layer 3: under the hood
            Column {
                visible: app.detailLevel === 2
                width: parent.width; spacing: Theme.sp2
                Repeater {
                    model: ins.shown ? ins.shown.hood : []
                    Txt {
                        required property string modelData
                        required property int index
                        width: column.width
                        text: modelData
                        kind: index < 2 ? "mono" : "md"
                        tone: index === 0 ? "primary" : "secondary"
                    }
                }
            }
            Txt { visible: app.detailLevel === 2 && ins.shown && ins.shown.terms.length > 0; text: T.termsTitle; kind: "sm"; strong: true }
            Flow {
                visible: app.detailLevel === 2
                width: parent.width; spacing: Theme.sp1
                Repeater { model: ins.shown ? ins.shown.terms : []
                           Chip { required property var modelData; text: modelData.name; clickable: true; onClicked: app.runPalette("glossary:" + modelData.key) } }
            }
            // Layer 4: why it is safe
            Column {
                visible: app.detailLevel === 3
                width: parent.width; spacing: Theme.sp2
                Txt { width: parent.width; text: ins.shown ? ins.shown.safe : "" }
                Txt { width: parent.width; visible: ins.shown && ins.shown.simplification.length > 0; tone: "secondary"
                      text: ins.shown ? T.simplification + ins.shown.simplification : "" }
            }
            Txt { width: parent.width; tone: "tertiary"; kind: "sm"; text: ins.shown ? T.metaphor + ins.shown.metaphor : "" }

            // The whole session: scrub back through earlier steps and replay any of them.
            Rectangle { width: parent.width; height: 1; color: Theme.hair }
            Txt { width: parent.width; kind: "sm"; strong: true; text: T.stageTimeline; visible: ins.override === null }
            SessionTimeline { width: parent.width; current: ins.index; visible: ins.override === null; onChosen: (i) => ins.jump(i) }
        }
    }
}
