// The Step Inspector: one recorded step at four levels of detail, with a player that
// replays the record. Nothing here is computed in QML: the record comes from Python.
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
    padding: Theme.s24
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

    Lbl { visible: ins.shown === null; anchors.centerIn: parent; width: parent.width - 20; horizontalAlignment: Text.AlignHCenter; text: T.inspectorEmpty; tone: "secondary" }

    Flickable {
        visible: ins.shown !== null
        anchors.fill: parent
        contentHeight: column.implicitHeight
        clip: true
        Column {
            id: column
            width: parent.width
            spacing: 12

            Item {
                width: parent.width; height: head.implicitHeight
                Column {
                    id: head
                    width: parent.width - 48
                    Row {
                        spacing: 10
                        Avatar { who: ins.shown ? (ins.shown.tag === "receiver" ? ins.shown.who : ins.shown.tagLabel) : ""; size: 30
                                 color: Theme.roleColor(ins.shown ? (ins.shown.tag === "receiver" ? ins.shown.who : ins.shown.tag) : "") }
                        Lbl { text: ins.shown ? ins.shown.title : ""; size: Theme.headline * 0.85; strong: true }
                    }
                    Lbl { text: ins.shown ? ins.shown.technical + (ins.shown.scope === "practice" ? " (on a practice copy)" : "") : ""; tone: "secondary"; size: Theme.caption; width: parent.width }
                }
                PButton { anchors.right: parent.right; quiet: true; text: T.close; onClicked: ins.close() }
            }

            Segmented {
                width: parent.width
                name: "Detail level"
                labels: width > 430 * Theme.scale ? [T.layerPlain, T.layerMoved, T.layerHood, T.layerSafe]
                                                 : [T.layerPlainShort, T.layerMovedShort, T.layerHoodShort, T.layerSafeShort]
                current: app.detailLevel
                onChosen: (i) => app.setDetailLevel(i)
            }

            // The picture of this step is visible at every level: it is the anchor.
            Rectangle {
                width: parent.width
                height: 190
                radius: Theme.rCard
                color: Theme.tint(Theme.roomTop, 0.6)
                border.width: 1; border.color: Theme.tint(Theme.glassStroke, 0.6)
                clip: true
                Loader {
                    anchors.fill: parent; anchors.margins: 12
                    active: ins.shown !== null
                    source: !ins.shown ? "" : ins.shown.kind.indexOf("attack:") === 0 ? "AnimAttack.qml" : ({ encrypt: "AnimEncrypt.qml", kem: "AnimKem.qml", sign: "AnimSign.qml",
                                                 search: "AnimSearch.qml", verify: "AnimVerify.qml" })[ins.shown.anim] || "AnimMove.qml"
                    onLoaded: {
                        item.record = Qt.binding(function () { return ins.shown })
                        item.progress = Qt.binding(function () { return ins.progress })
                    }
                }
            }
            Lbl { width: parent.width; tone: "muted"; size: Theme.caption; text: ins.shown ? ins.shown.replayNote : "" }

            Row {
                spacing: 6
                PButton { text: T.stepBack; implicitWidth: 74; onClicked: ins.toStep(ins.step - 1) }
                PButton { text: ins.playing ? T.pause : T.play; primary: true; implicitWidth: 84; onClicked: ins.playing ? ins.pause() : ins.play() }
                PButton { text: T.stepNext; implicitWidth: 74; onClicked: ins.toStep(ins.step + 1) }
                PButton { text: T.replay; implicitWidth: 84; onClicked: ins.replay() }
                PButton {
                    text: ins.speed + "x"
                    implicitWidth: 70
                    Accessible.name: T.speed + " " + ins.speed
                    onClicked: ins.speed = ins.speeds[(ins.speeds.indexOf(ins.speed) + 1) % ins.speeds.length]
                }
            }
            Rectangle {          // scrubber of this step
                width: parent.width; height: 6; radius: 3
                color: Theme.tint(Theme.glassRaised, 1)
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
                width: parent.width; spacing: 8
                Lbl { width: parent.width; text: ins.shown ? ins.shown.line : ""; size: Theme.bodyLarge; strong: true }
                Lbl { width: parent.width; text: ins.shown ? ins.shown.more : ""; tone: "secondary"; size: Theme.bodyLarge * 0.95 }
            }
            // Layer 2: what moved, as a numbered timeline
            Column {
                visible: app.detailLevel === 1
                width: parent.width; spacing: 6
                Repeater {
                    model: ins.shown ? ins.shown.steps : []
                    Item {
                        id: stepRow
                        required property string modelData
                        required property int index
                        width: column.width
                        height: Math.max(30, stepText.implicitHeight + 8)
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: "Step " + (index + 1) + ": " + modelData
                        Keys.onReturnPressed: ins.toStep(index)
                        Rectangle {
                            width: 26; height: 26; radius: 13
                            color: stepRow.index === ins.step ? Theme.accent : stepRow.index < ins.step ? Theme.ok : Theme.tint(Theme.glassRaised, 1)
                            border.width: stepRow.activeFocus ? 2 : 0; border.color: Theme.textPrimary
                            Text {
                                anchors.centerIn: parent
                                text: stepRow.index < ins.step ? "✓" : stepRow.index + 1
                                color: stepRow.index <= ins.step ? Theme.accentOn : Theme.textSecondary
                                font.pixelSize: Theme.caption; font.weight: Font.DemiBold; font.family: Theme.fontFamily
                            }
                        }
                        Lbl {
                            id: stepText
                            x: 38; width: parent.width - 38
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
                width: parent.width; spacing: 6
                Repeater {
                    model: ins.shown ? ins.shown.hood : []
                    Lbl {
                        required property string modelData
                        required property int index
                        width: column.width
                        text: modelData
                        font.family: index < 2 ? Theme.monoFamily : Theme.fontFamily
                        tone: index === 0 ? "primary" : "secondary"
                        strong: index === 0
                    }
                }
            }
            // Layer 4: why it is safe
            Column {
                visible: app.detailLevel === 3
                width: parent.width; spacing: 8
                Lbl { width: parent.width; text: ins.shown ? ins.shown.safe : ""; size: Theme.bodyLarge * 0.95 }
                Lbl { width: parent.width; visible: ins.shown && ins.shown.simplification.length > 0; tone: "secondary"
                      text: ins.shown ? T.simplification + ins.shown.simplification : "" }
            }
            Lbl { width: parent.width; tone: "muted"; size: Theme.caption; text: ins.shown ? T.metaphor + ins.shown.metaphor : "" }

            // The whole session: scrub back through earlier steps and replay any of them.
            Rectangle { width: parent.width; height: 1; color: Theme.tint(Theme.glassStroke, 0.5) }
            Lbl { width: parent.width; tone: "muted"; size: Theme.caption; text: T.stageTimeline; visible: ins.override === null }
            SessionTimeline { width: parent.width; current: ins.index; visible: ins.override === null; onChosen: (i) => ins.jump(i) }
        }
    }
}
