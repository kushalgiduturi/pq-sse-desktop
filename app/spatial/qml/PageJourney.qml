// Journey: the guided lesson. The steps run on the real system in the practice area.
// (The fully visual path, challenges and "Let me try" arrive in milestone 5.)
import QtQuick

Item {
    id: page
    signal inspect(int index)
    readonly property var steps: app.lessonSteps
    readonly property int current: app.lessonStep
    readonly property var step: steps[current]
    function isDone(key) { return app.lessonDone.indexOf(key) >= 0 }

    Column {
        id: header
        width: parent.width
        spacing: 4
        Lbl { text: T.journeyTitle; size: Theme.display; strong: true }
        Lbl { text: T.journeySub; tone: "secondary"; size: Theme.bodyLarge; width: parent.width }
    }

    // the path
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
                    Accessible.name: "Step " + (index + 1) + ": " + modelData.title + (done ? ". " + T.journeyDone : "")
                    Keys.onReturnPressed: app.setLessonStep(index)
                    Rectangle {          // link to the next step
                        visible: node.index < page.steps.length - 1
                        x: parent.width / 2 + 16; y: 16
                        width: parent.width - 32; height: 3; radius: 2
                        color: node.done ? Theme.ok : Theme.tint(Theme.glassStroke, 0.7)
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: node.on ? 0 : 4
                        width: node.on ? 34 : 26; height: width; radius: width / 2
                        color: node.done ? Theme.ok : node.on ? Theme.accent : Theme.tint(Theme.glassRaised, 1)
                        border.width: node.on || node.activeFocus ? 3 : 1
                        border.color: node.on || node.activeFocus ? Theme.textPrimary : Theme.tint(Theme.glassStroke, 0.8)
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
                        y: 40
                        width: Math.max(parent.width, 170); horizontalAlignment: Text.AlignHCenter
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

    // the focused step
    Glass {
        id: focus
        anchors.top: path.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: parent.bottom
        width: parent.width * 0.62
        rim: Theme.accent; rimWidth: 2
        Flickable {
            anchors.fill: parent
            anchors.bottomMargin: actions.height + 12
            contentHeight: text.implicitHeight
            clip: true
            Column {
                id: text
                width: parent.width
                spacing: 10
                Chip { text: "Step " + (page.current + 1) + " of " + page.steps.length; mark: page.isDone(page.step.key) ? "ok" : "" }
                Lbl { width: parent.width; text: page.step.title; size: Theme.headline; strong: true }
                Lbl {
                    width: parent.width
                    text: page.step.explain
                    textFormat: Text.RichText
                    tone: "secondary"; size: Theme.bodyLarge * 0.95
                    onLinkActivated: (link) => app.runPalette(link)
                    HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                }
            }
        }
        Row {
            id: actions
            anchors.bottom: parent.bottom
            spacing: 10
            PButton { visible: page.step.runnable; primary: true; enabled: !app.busy; text: T.journeyRun; onClicked: app.runLessonStep(page.current) }
            PButton { enabled: page.current > 0; text: T.journeyBack; onClicked: app.setLessonStep(page.current - 1) }
            PButton { enabled: page.current < page.steps.length - 1; primary: !page.step.runnable; text: T.journeyNext; onClicked: app.setLessonStep(page.current + 1) }
        }
    }

    // what just happened, and housekeeping
    Glass {
        anchors.top: path.bottom; anchors.topMargin: Theme.s16
        anchors.left: focus.right; anchors.leftMargin: Theme.s16
        anchors.right: parent.right
        anchors.bottom: house.top; anchors.bottomMargin: Theme.s16
        Flickable {
            anchors.fill: parent
            contentHeight: result.implicitHeight
            clip: true
            Column {
                id: result
                width: parent.width
                spacing: 8
                Lbl { text: "What just happened"; size: Theme.title; strong: true }
                Lbl {
                    width: parent.width
                    textFormat: Text.RichText
                    tone: "secondary"
                    text: app.lessonResult.length > 0 ? app.lessonResult : "Run the step. What it did on the real system appears here, and on the Stage."
                    onLinkActivated: (link) => app.runPalette(link)
                }
                PButton { visible: events.count > 0; text: T.inspectorOpen; onClicked: page.inspect(events.count - 1) }
            }
        }
    }
    Glass {
        id: house
        anchors.left: focus.right; anchors.leftMargin: Theme.s16
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: houseColumn.implicitHeight + 2 * padding
        Column {
            id: houseColumn
            width: parent.width
            spacing: 8
            Lbl { width: parent.width; text: T.journeyResetNote; tone: "secondary"; size: Theme.caption }
            Row {
                spacing: 10
                PButton { text: T.journeyReset; enabled: !app.busy; onClicked: app.resetLesson() }
                PButton { visible: app.practice; text: T.journeyLeave; enabled: !app.busy; onClicked: app.leavePractice() }
            }
        }
    }
}
