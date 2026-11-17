// Journey: the guided lesson as a path of steps. Each step can be run for you on the real
// system ("Run this step for me") or done by hand ("Let me try", then "Check my work").
// Challenges sit beside it. Everything happens in the practice area.
import QtQuick

Item {
    id: page
    signal inspect(int index)
    readonly property var steps: app.lessonSteps
    readonly property int current: app.lessonStep
    readonly property var step: steps[current]
    readonly property var challenges: app.challengeList
    readonly property int challengesDone: challenges.filter(function (c) { return c.done }).length
    property string hintFor: ""
    function isDone(key) { return app.lessonDone.indexOf(key) >= 0 }
    function fill(text, map) { for (var k in map) text = text.split("{" + k + "}").join(map[k]); return text }

    // At 150 % and 200 % text the page stacks into one scrolling column; otherwise it fits the window.
    Flickable {
    id: scroll
    anchors.fill: parent
    contentHeight: board.height
    interactive: Theme.large
    clip: true
    Item {
    id: board
    width: scroll.width
    height: Theme.large ? side.y + sideColumn.implicitHeight + 16 : scroll.height

    Column {
        id: header
        width: parent.width
        spacing: 4
        Lbl { text: T.journeyTitle; size: Theme.display; strong: true }
        Lbl { text: T.journeySub; tone: "secondary"; size: Theme.bodyLarge; width: parent.width }
    }

    // ---------------------------------------------------------------- the path
    Glass {
        id: path
        anchors.top: header.bottom; anchors.topMargin: Theme.s16
        width: parent.width
        height: 96 * Math.max(1, Theme.scale)
        padding: Theme.s16
        Row {
            anchors.fill: parent
            Repeater {
                model: page.steps
                Item {
                    id: node
                    required property var modelData
                    required property int index
                    readonly property bool done: page.isDone(modelData.key)
                    readonly property bool on: index === page.current
                    width: parent.width / page.steps.length
                    height: parent.height
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: page.fill(T.journeyStepOf, { n: index + 1, all: page.steps.length }) + ": " + modelData.title
                                     + (on ? ". " + T.journeyCurrent : "") + (done ? ". " + T.journeyDone : "")
                    Keys.onReturnPressed: app.setLessonStep(index)
                    Keys.onSpacePressed: app.setLessonStep(index)
                    Rectangle {
                        visible: node.index < page.steps.length - 1
                        x: parent.width / 2 + 18; y: 16
                        width: parent.width - 36; height: 3; radius: 2
                        color: node.done ? Theme.ok : Theme.hairStrong
                        Behavior on color { ColorAnimation { duration: Theme.slow } }
                    }
                    Rectangle {          // the current step has a soft ring around it
                        visible: node.on
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: -5; width: 44; height: 44; radius: 22
                        color: Theme.tint(Theme.accent, 0.25)
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: node.on ? 0 : 4
                        width: node.on ? 34 : 26; height: width; radius: width / 2
                        color: node.done ? Theme.ok : node.on ? Theme.accent : Theme.hover
                        border.width: node.on || node.activeFocus ? 3 : 1
                        border.color: node.on || node.activeFocus ? Theme.textPrimary : Theme.hairStrong
                        Behavior on width { NumberAnimation { duration: Theme.moveBase; easing.type: Easing.OutBack } }
                        Text {
                            anchors.centerIn: parent
                            text: node.done ? "✓" : node.index + 1
                            color: node.done || node.on ? Theme.accentOn : Theme.textSecondary
                            font.family: Theme.fontFamily; font.pixelSize: Theme.caption; font.weight: Font.DemiBold
                        }
                    }
                    Lbl {
                        visible: node.on || hov.hovered || node.activeFocus
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 42
                        width: Math.max(parent.width, 190); horizontalAlignment: Text.AlignHCenter
                        text: node.modelData.title
                        size: Theme.caption; strong: node.on
                        maximumLineCount: 1; elide: Text.ElideRight; wrapMode: Text.NoWrap
                    }
                    HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.setLessonStep(node.index) }
                }
            }
        }
    }

    // ---------------------------------------------------------------- the focused step
    Glass {
        id: focus
        anchors.top: path.bottom; anchors.topMargin: Theme.s16
        height: Theme.large ? text.implicitHeight + actions.height + 2 * padding + 16 : board.height - y
        width: Theme.large ? parent.width : parent.width * 0.60
        rim: Theme.accent; rimWidth: 2
        Flickable {
            anchors.fill: parent
            anchors.bottomMargin: actions.height + 12
            contentHeight: text.implicitHeight
            interactive: !Theme.large
            clip: true
            Column {
                id: text
                width: parent.width
                spacing: 10
                Chip { text: page.fill(T.journeyStepOf, { n: page.current + 1, all: page.steps.length }); mark: page.isDone(page.step.key) ? "ok" : "" }
                Lbl { width: parent.width; text: page.step.title; size: Theme.headline; strong: true }
                Lbl {
                    width: parent.width
                    text: page.step.explain
                    textFormat: Text.RichText
                    tone: "secondary"; size: Theme.bodyLarge * 0.95
                    onLinkActivated: (link) => app.runPalette(link)
                }
                Rectangle {          // the result of "Check my work"
                    visible: app.lessonCheck.step === page.current
                    width: parent.width; height: checkText.implicitHeight + 20; radius: 12
                    color: Theme.tint(app.lessonCheck.ok ? Theme.ok : Theme.warn, 0.16)
                    border.width: 1; border.color: app.lessonCheck.ok ? Theme.ok : Theme.warn
                    Lbl { id: checkText; x: 12; width: parent.width - 24; anchors.verticalCenter: parent.verticalCenter
                          text: (app.lessonCheck.ok ? "✓ " : "⚠ ") + (app.lessonCheck.text || "") }
                }
            }
        }
        Flow {
            id: actions
            anchors.bottom: parent.bottom
            width: parent.width
            spacing: 10
            PButton { visible: page.step.runnable; primary: true; enabled: !app.busy; text: T.journeyRun; onClicked: app.runLessonStep(page.current) }
            PButton { visible: page.step.runnable; enabled: !app.busy; text: T.journeyTry; onClicked: app.tryLessonStep(page.current) }
            PButton { visible: page.step.runnable; enabled: !app.busy; text: T.journeyCheck; onClicked: app.checkLessonStep(page.current) }
            PButton { enabled: page.current > 0; text: T.journeyBack; onClicked: app.setLessonStep(page.current - 1) }
            PButton { enabled: page.current < page.steps.length - 1; primary: !page.step.runnable; text: T.journeyNext; onClicked: app.setLessonStep(page.current + 1) }
        }
    }

    // ---------------------------------------------------------------- what happened, challenges, reset
    Flickable {
        id: side
        x: Theme.large ? 0 : focus.width + Theme.s16
        y: Theme.large ? focus.y + focus.height + Theme.s16 : focus.y
        width: Theme.large ? parent.width : parent.width - focus.width - Theme.s16
        height: Theme.large ? sideColumn.implicitHeight + 12 : board.height - y
        contentHeight: sideColumn.implicitHeight + 12
        interactive: !Theme.large
        clip: true
        Column {
            id: sideColumn
            width: parent.width
            spacing: Theme.s16

            TaskCard {
                width: parent.width
                title: T.journeyHappened
                Lbl {
                    width: parent.width
                    textFormat: Text.RichText
                    tone: "secondary"
                    text: app.lessonResult.length > 0 ? app.lessonResult : T.journeyHappenedEmpty
                    onLinkActivated: (link) => app.runPalette(link)
                }
                PButton { visible: events.count > 0; text: T.inspectorOpen; onClicked: page.inspect(events.count - 1) }
            }

            TaskCard {
                width: parent.width
                title: T.journeyChallenges
                summary: page.fill(T.journeyChallengesSub, { done: page.challengesDone, all: page.challenges.length })
                Rectangle {
                    width: parent.width; height: 8; radius: 4; color: Theme.hover
                    Rectangle { width: parent.width * page.challengesDone / Math.max(1, page.challenges.length); height: 8; radius: 4; color: Theme.ok
                                Behavior on width { NumberAnimation { duration: Theme.moveSlow; easing.type: Easing.OutCubic } } }
                }
                Repeater {
                    model: page.challenges
                    Column {
                        id: item
                        required property var modelData
                        width: parent.width
                        spacing: 4
                        Row {
                            spacing: 8
                            Text { width: 16; text: item.modelData.done ? "✓" : "○"; color: item.modelData.done ? Theme.ok : Theme.textMuted
                                   font.pixelSize: Theme.bodyLarge; font.weight: Font.Bold
                                   Accessible.name: item.modelData.done ? T.journeyDone : T.notChecked }
                            Lbl { width: item.width - 28; text: item.modelData.title; strong: true }
                        }
                        Lbl { x: 24; width: parent.width - 24; text: item.modelData.task; tone: "secondary"; size: Theme.caption }
                        Lbl { x: 24; width: parent.width - 24; visible: page.hintFor === item.modelData.key; text: item.modelData.hint; size: Theme.caption }
                        Row {
                            x: 16; spacing: 4
                            visible: !item.modelData.done
                            PButton { quiet: true; text: T.journeyHint; Accessible.name: T.journeyHint + ": " + item.modelData.title; onClicked: page.hintFor = page.hintFor === item.modelData.key ? "" : item.modelData.key }
                            PButton { quiet: true; text: T.journeyGo; Accessible.name: T.journeyGo + ": " + item.modelData.title; onClicked: app.navigate(item.modelData.where) }
                        }
                    }
                }
            }

            TaskCard {
                width: parent.width
                title: T.journeyLesson
                summary: T.journeyResetNote
                Row {
                    spacing: 10
                    PButton { text: T.journeyReset; enabled: !app.busy; onClicked: { app.resetLesson(); app.resetChallenges() } }
                    PButton { visible: app.practice; text: T.journeyLeave; enabled: !app.busy; onClicked: app.leavePractice() }
                }
            }
        }
    }
    }
    }
}
