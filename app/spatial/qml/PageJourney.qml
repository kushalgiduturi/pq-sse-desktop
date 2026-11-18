// Journey: the guided lesson as a path of steps. Each step can be run for you on the real
// system ("Run this step for me") or done by hand ("Let me try", then "Check my work").
// Challenges sit beside it. Everything happens in the practice area.
// Quiet glass: the path is a segmented track (no numbered chips), the step and the side
// column are flat areas of the page panel divided by a hairline.
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
        spacing: Theme.sp1
        Txt { text: T.journeyTitle; kind: "xl"; width: parent.width }
        Txt { text: T.journeySub; tone: "secondary"; width: Math.min(parent.width, 760) }
    }

    // ---------------------------------------------------------------- the path
    Item {
        id: path
        anchors.top: header.bottom; anchors.topMargin: Theme.sp6
        width: parent.width
        height: 40
        Txt {
            id: count
            anchors.right: parent.right
            y: 6
            text: (page.current + 1) + " / " + page.steps.length
            kind: "mono"; tone: "secondary"; lineHeight: 1.0
        }
        Row {
            id: track
            width: parent.width - count.width - Theme.sp4
            spacing: 4
            Repeater {
                model: page.steps
                Item {
                    id: node
                    required property var modelData
                    required property int index
                    readonly property bool done: page.isDone(modelData.key)
                    readonly property bool on: index === page.current
                    width: (track.width - (page.steps.length - 1) * track.spacing) / page.steps.length
                    height: Theme.touch ? 44 : 28
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: page.fill(T.journeyStepOf, { n: index + 1, all: page.steps.length }) + ": " + modelData.title
                                     + (on ? ". " + T.journeyCurrent : "") + (done ? ". " + T.journeyDone : "")
                    Keys.onReturnPressed: app.setLessonStep(index)
                    Keys.onSpacePressed: app.setLessonStep(index)
                    // one segment: done = text color, current = accent and taller, later = hairline
                    Rectangle {
                        y: 10 - (node.on ? 2 : 0)
                        width: parent.width
                        height: node.on ? 8 : 4
                        radius: height / 2
                        color: node.on ? Theme.accent : node.done ? Theme.text2 : Theme.hairStrong
                        Behavior on color { ColorAnimation { duration: Theme.dur3 } }
                        Behavior on height { NumberAnimation { duration: Theme.dur2; easing.type: Easing.OutBack; easing.overshoot: Theme.springOvershoot } }
                    }
                    Rectangle {
                        visible: node.activeFocus
                        anchors.fill: parent; anchors.margins: -2
                        radius: Theme.rSm; color: "transparent"; border.width: 2; border.color: Theme.ring
                    }
                    HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.setLessonStep(node.index) }
                    // the title of a hovered or focused step, as a small tooltip above the track
                    Surface {
                        visible: (hov.hovered || node.activeFocus) && !node.on
                        depth: 4; blur: false; radius: Theme.rSm; padding: 0
                        z: 20
                        width: tip.implicitWidth + 20; height: tip.implicitHeight + 10
                        x: Math.max(-node.x, Math.min(node.width / 2 - width / 2, track.width - node.x - width))
                        y: 30
                        Txt { id: tip; anchors.centerIn: parent; text: node.modelData.title; kind: "sm"; wrapMode: Text.NoWrap; lineHeight: 1.2 }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- the focused step
    Glass {
        id: focus
        anchors.top: path.bottom; anchors.topMargin: Theme.sp4
        height: Theme.large ? text.implicitHeight + actions.height + 16 : board.height - y
        width: Theme.large ? parent.width : parent.width * 0.60 - Theme.sp8
        Flickable {
            anchors.fill: parent
            anchors.bottomMargin: actions.height + Theme.sp4
            contentHeight: text.implicitHeight
            interactive: !Theme.large
            clip: true
            Column {
                id: text
                width: parent.width
                spacing: Theme.sp3
                Row {
                    width: parent.width
                    spacing: Theme.sp3
                    Txt { id: stepTitle; text: page.step.title; kind: "xl"; width: Math.min(implicitWidth, parent.width - (donePill.visible ? donePill.width + 12 : 0)) }
                    Pill { id: donePill; visible: page.isDone(page.step.key); text: T.journeyDone; status: "ok"; anchors.verticalCenter: stepTitle.verticalCenter }
                }
                Txt {
                    width: parent.width
                    text: page.step.explain
                    textFormat: Text.RichText
                    tone: "secondary"
                    onLinkActivated: (link) => app.runPalette(link)
                }
                Item {               // the result of "Check my work": an inset with a status icon
                    visible: app.lessonCheck.step === page.current
                    width: parent.width; height: checkText.implicitHeight + 24
                    Surface { anchors.fill: parent; depth: 1; radius: Theme.rCard; padding: 0 }
                    Icon { x: 16; y: 14; name: app.lessonCheck.ok ? "check" : "alert"; size: 18; color: app.lessonCheck.ok ? Theme.ok : Theme.warn }
                    Txt { id: checkText; x: 44; width: parent.width - 60; anchors.verticalCenter: parent.verticalCenter
                          text: app.lessonCheck.text || "" }
                }
            }
        }
        Flow {
            id: actions
            anchors.bottom: parent.bottom
            width: parent.width
            spacing: Theme.sp2
            PButton { visible: page.step.runnable; primary: true; enabled: !app.busy; text: T.journeyRun; onClicked: app.runLessonStep(page.current) }
            PButton { visible: page.step.runnable; enabled: !app.busy; text: T.journeyTry; onClicked: app.tryLessonStep(page.current) }
            PButton { visible: page.step.runnable; enabled: !app.busy; text: T.journeyCheck; onClicked: app.checkLessonStep(page.current) }
            PButton { enabled: page.current > 0; quiet: true; text: T.journeyBack; onClicked: app.setLessonStep(page.current - 1) }
            PButton { enabled: page.current < page.steps.length - 1; primary: !page.step.runnable; text: T.journeyNext; onClicked: app.setLessonStep(page.current + 1) }
        }
    }

    Rectangle {
        visible: !Theme.large
        x: focus.width + Theme.sp8; y: focus.y
        width: 1; height: focus.height
        color: Theme.hair
    }
    // ---------------------------------------------------------------- what happened, challenges, reset
    Flickable {
        id: side
        x: Theme.large ? 0 : focus.width + 2 * Theme.sp8
        y: Theme.large ? focus.y + focus.height + Theme.sp8 : focus.y
        width: Theme.large ? parent.width : parent.width - focus.width - 2 * Theme.sp8
        height: Theme.large ? sideColumn.implicitHeight + 12 : board.height - y
        contentHeight: sideColumn.implicitHeight + 12
        interactive: !Theme.large
        clip: true
        Column {
            id: sideColumn
            width: parent.width
            spacing: Theme.sp8

            TaskCard {
                width: parent.width
                title: T.journeyHappened
                Txt {
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
                Item {
                    width: parent.width; height: 6
                    Surface { anchors.fill: parent; depth: 1; radius: 3; padding: 0 }
                    Rectangle { width: parent.width * page.challengesDone / Math.max(1, page.challenges.length); height: 6; radius: 3; color: Theme.ok
                                Behavior on width { NumberAnimation { duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } } }
                }
                Repeater {
                    model: page.challenges
                    Column {
                        id: item
                        required property var modelData
                        width: parent.width
                        spacing: 2
                        topPadding: Theme.sp2
                        Row {
                            spacing: Theme.sp2
                            Item {
                                width: 18; height: 18
                                anchors.verticalCenter: parent.verticalCenter
                                Accessible.role: Accessible.StaticText
                                Accessible.name: item.modelData.done ? T.journeyDone : T.notChecked
                                Icon { visible: item.modelData.done; anchors.centerIn: parent; name: "check"; size: 18; color: Theme.ok }
                                Rectangle { visible: !item.modelData.done; anchors.centerIn: parent; width: 14; height: 14; radius: 7
                                            color: "transparent"; border.width: 1.5; border.color: Theme.hairStrong }
                            }
                            Txt { width: item.width - 28; text: item.modelData.title; strong: true; lineHeight: 1.3 }
                        }
                        Txt { x: 26; width: parent.width - 26; text: item.modelData.task; tone: "secondary"; kind: "sm" }
                        Txt { x: 26; width: parent.width - 26; visible: page.hintFor === item.modelData.key; text: item.modelData.hint; kind: "sm" }
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
                Flow {
                    width: parent.width
                    spacing: Theme.sp2
                    PButton { text: T.journeyReset; enabled: !app.busy; onClicked: { app.resetLesson(); app.resetChallenges() } }
                    PButton { visible: app.practice; text: T.journeyLeave; enabled: !app.busy; onClicked: app.leavePractice() }
                }
                Switch { width: parent.width; text: T.journeyTeaching; help: T.journeyTeachingNote
                         checked: app.teachingNames; onToggled: (on) => app.setTeachingNames(on) }
            }
        }
    }
    }
    }
}
