// Security Lab: every attack as a card. Choosing a card opens it next to the grid with the
// attacker's attempt, the check that reacts, and what would happen without the protection.
// Each attack runs for real on a throwaway copy. The policy comparison is side by side.
import QtQuick

Item {
    id: lab
    property string chosen: ""
    signal inspect(var record)
    readonly property var attacks: app.attacks
    readonly property var normal: attacks.filter(function (a) { return a.key !== "collusion" })
    readonly property var collusion: { for (var i = 0; i < attacks.length; i++) if (attacks[i].key === "collusion") return attacks[i]; return null }
    readonly property var current: { for (var i = 0; i < attacks.length; i++) if (attacks[i].key === chosen) return attacks[i]; return null }
    property real progress: 0
    function replay() { progress = 0; if (Theme.reduceMotion) progress = 1; else player.restart() }
    onCurrentChanged: replay()
    NumberAnimation { id: player; target: lab; property: "progress"; from: 0; to: 1; duration: 3200 }
    Connections { target: app; function onAttackFinished(key) { if (key === lab.chosen) lab.replay() } }

    Column {
        id: header
        width: parent.width
        spacing: 4
        Lbl { text: T.labTitle; size: Theme.display; strong: true }
        Lbl { text: T.labSub; tone: "secondary"; size: Theme.bodyLarge; width: parent.width }
    }

    Flickable {
        id: grid
        anchors.top: header.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: parent.bottom
        width: parent.width * 0.54
        contentHeight: flow.implicitHeight + 12
        clip: true
        Flow {
            id: flow
            width: parent.width
            spacing: Theme.s12
            Repeater {
                model: lab.normal
                Glass {
                    id: card
                    required property var modelData
                    readonly property bool on: lab.chosen === modelData.key
                    width: (flow.width - Theme.s12) / 2
                    height: Math.max(132, inside.implicitHeight + 2 * padding)
                    radius: Theme.rCard
                    padding: Theme.s16
                    rim: on ? Theme.attacker : Theme.glassStroke
                    rimWidth: on || activeFocus ? 2 : 1
                    scale: hover.hovered && !Theme.reduceMotion ? 1.02 : 1
                    Behavior on scale { SpringAnimation { spring: Theme.hoverSpring; damping: Theme.hoverDamping } }
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.title + ". " + modelData.line + ". " + (modelData.ran ? (modelData.passed ? "Caught by " + modelData.caughtBy : T.labNotCaught) : T.labNotRun)
                    Keys.onReturnPressed: lab.chosen = modelData.key
                    Keys.onSpacePressed: lab.chosen = modelData.key
                    Column {
                        id: inside
                        width: parent.width
                        spacing: 6
                        Row { spacing: 8
                              Rectangle { width: 24; height: 24; radius: 12; color: Theme.attacker
                                          Lbl { anchors.centerIn: parent; text: "!"; color: Theme.onRole; size: Theme.caption; strong: true } }
                              Lbl { text: card.modelData.title; strong: true; size: Theme.bodyLarge; width: inside.width - 36 } }
                        Lbl { width: parent.width; text: card.modelData.line; tone: "secondary"; size: Theme.caption }
                        Chip { maxWidth: parent.width
                               mark: card.modelData.running ? "dot" : !card.modelData.ran ? "" : card.modelData.passed ? "ok" : "fail"
                               dot: Theme.warn
                               text: card.modelData.running ? T.labRunning : !card.modelData.ran ? T.labNotRun
                                   : card.modelData.passed ? T.labCaught.replace("{by}", card.modelData.caughtBy) : T.labNotCaught }
                    }
                    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: lab.chosen = card.modelData.key }
                }
            }
        }
    }

    Flickable {
        anchors.top: header.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: parent.bottom
        anchors.left: grid.right; anchors.leftMargin: Theme.s16
        anchors.right: parent.right
        contentHeight: side.implicitHeight + 12
        clip: true
        Column {
            id: side
            width: parent.width
            spacing: Theme.s16

            // ---- the chosen attack
            TaskCard {
                visible: lab.current !== null
                width: parent.width
                title: lab.current ? lab.current.title : ""
                rim: Theme.attacker
                Lbl { text: T.labTries; tone: "muted"; size: Theme.caption; strong: true }
                Lbl { width: parent.width; text: lab.current ? lab.current.tries : ""; tone: "secondary" }
                Rectangle {
                    width: parent.width; height: 250 * Math.max(1, Theme.scale); radius: Theme.rCard
                    color: Theme.tint(Theme.roomTop, 0.6); border.width: 1; border.color: Theme.tint(Theme.glassStroke, 0.6)
                    AnimAttack { anchors.fill: parent; anchors.margins: 12; record: lab.current; progress: lab.progress }
                }
                Lbl { width: parent.width; text: T.labAttackerPicture; tone: "muted"; size: Theme.caption }
                Lbl { visible: lab.current && lab.current.ran; text: T.labCheck; tone: "muted"; size: Theme.caption; strong: true }
                Lbl { visible: lab.current && lab.current.ran; width: parent.width
                      text: lab.current ? (lab.current.passed ? lab.current.caughtBy + ". " : "") + lab.current.verdict : "" }
                Lbl { text: T.labWithout; tone: "muted"; size: Theme.caption; strong: true }
                Lbl { width: parent.width; text: lab.current ? lab.current.without : ""; tone: "secondary" }
                Row { spacing: 10
                      PButton { primary: true; enabled: lab.current && !lab.current.running
                                text: lab.current && lab.current.ran ? T.labRunAgain : T.labRun
                                onClicked: app.runAttack(lab.chosen) }
                      PButton { visible: lab.current && lab.current.ran; text: T.replay; onClicked: lab.replay() }
                      PButton { visible: lab.current && lab.current.ran; text: T.inspectorOpen; onClicked: lab.inspect(lab.current) } }
                Repeater {
                    model: lab.current && app.mode === "expert" ? lab.current.lines : []
                    Lbl { required property string modelData; width: parent.width; text: modelData; tone: "muted"; size: Theme.caption }
                }
            }

            // ---- policy R versus policy RE, side by side
            TaskCard {
                width: parent.width
                title: T.labCompareTitle
                summary: T.labCompareIntro
                Row {
                    width: parent.width
                    spacing: Theme.s12
                    Repeater {
                        model: [{ name: T.labCompareR, note: T.labCompareRNote, safe: false, line: 1 },
                                { name: T.labCompareRE, note: T.labCompareRENote, safe: true, line: 2 }]
                        Rectangle {
                            id: column
                            required property var modelData
                            width: (parent.width - Theme.s12) / 2
                            height: columnBody.implicitHeight + 28
                            radius: Theme.rCard
                            color: Theme.tint(Theme.glassRaised, 0.8)
                            border.width: 2; border.color: modelData.safe ? Theme.ok : Theme.fail
                            Column {
                                id: columnBody
                                x: 14; y: 14; width: parent.width - 28; spacing: 8
                                Lbl { text: column.modelData.name; strong: true; size: Theme.bodyLarge }
                                Chip { maxWidth: parent.width; mark: column.modelData.safe ? "ok" : "fail"
                                       text: column.modelData.safe ? "Old documents: locked" : "Old documents: still readable" }
                                Chip { maxWidth: parent.width; mark: "ok"; text: "New documents: locked" }
                                Lbl { width: parent.width; visible: lab.collusion && lab.collusion.ran && lab.collusion.lines.length > column.modelData.line
                                      text: lab.collusion && lab.collusion.lines.length > column.modelData.line ? "Measured: " + lab.collusion.lines[column.modelData.line] : ""
                                      size: Theme.caption }
                                Lbl { width: parent.width; text: column.modelData.note; tone: "secondary"; size: Theme.caption }
                            }
                        }
                    }
                }
                PButton { primary: lab.current === null; enabled: lab.collusion && !lab.collusion.running
                          text: lab.collusion && lab.collusion.running ? T.labRunning : T.labCompareRun
                          onClicked: app.runAttack("collusion") }
            }
        }
    }
}
