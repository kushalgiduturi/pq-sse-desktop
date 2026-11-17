// Security Lab: every attack as a row in a flat list. Choosing a row opens it on the right
// with the attacker's attempt, the check that reacts, and what would happen without the
// protection. Each attack runs for real on a throwaway copy. The policy comparison is side
// by side. Quiet glass: rows with hairlines, a status pill per row, no cards.
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
    function statusOf(a) { return a.running ? "warn" : !a.ran ? "neutral" : a.passed ? "ok" : "bad" }
    function shortText(a) { return a.running ? T.labRunningShort : !a.ran ? T.labNotRun : a.passed ? T.labCaughtWord : T.labNotCaught }
    function statusText(a) { return a.running ? T.labRunningShort : !a.ran ? T.labNotRun : a.passed ? T.labCaught.replace("{by}", a.caughtBy) : T.labNotCaught }
    // Shared-element transition: the chosen row's title travels to the detail heading, then
    // the detail fades in where it landed. With Reduce motion the detail just appears.
    function open(row, key) {
        if (key === chosen) return
        if (Theme.reduceMotion || lab.current === null) { chosen = key; return }
        var from = row.mapToItem(lab, 0, 0)
        var to = detailArea.mapToItem(lab, 0, 0)
        ghost.x = from.x - Theme.sp3; ghost.y = from.y; ghost.width = row.width + 2 * Theme.sp3; ghost.height = row.height
        ghost.title = row.modelData.title
        ghost.toX = to.x; ghost.toY = to.y; ghost.toW = detailArea.width; ghost.toH = Math.min(320, lab.height - to.y)
        ghost.pending = key
        grow.restart()
    }
    onCurrentChanged: replay()
    NumberAnimation { id: player; target: lab; property: "progress"; from: 0; to: 1; duration: 3200 }
    Connections { target: app; function onAttackFinished(key) { if (key === lab.chosen) lab.replay() } }

    Column {
        id: header
        width: parent.width
        spacing: Theme.sp1
        Txt { text: T.labTitle; kind: "xl"; width: parent.width }
        Txt { text: T.labSub; tone: "secondary"; width: Math.min(parent.width, 760) }
    }

    // ---------------------------------------------------------------- the list
    Flickable {
        id: list
        anchors.top: header.bottom; anchors.topMargin: Theme.sp6
        anchors.bottom: parent.bottom
        width: Theme.large ? parent.width : parent.width * 0.46
        contentHeight: rows.implicitHeight + Theme.sp3
        clip: true
        visible: !Theme.large || lab.current === null
        Column {
            id: rows
            x: Theme.sp3
            width: parent.width - 2 * Theme.sp3
            SectionTitle { text: T.labAttacks; count: String(lab.normal.length) }
            Repeater {
                model: lab.normal
                ListRow {
                    id: row
                    required property var modelData
                    width: rows.width
                    clickable: true
                    selected: lab.chosen === modelData.key
                    Accessible.name: Theme.fmt(T.labCardName, { title: modelData.title, line: modelData.line, state: modelData.ran ? (modelData.passed ? Theme.fmt(T.labCaughtShort, { by: modelData.caughtBy }) : T.labNotCaught) : T.labNotRun })
                    onClicked: lab.open(row, modelData.key)
                    Item {
                        width: row.width
                        height: Math.max(rowText.implicitHeight, rowPill.height)
                        Column {
                            id: rowText
                            width: parent.width - rowPill.width - Theme.sp4
                            spacing: 2
                            Txt { width: parent.width; text: row.modelData.title; strong: true; lineHeight: 1.3 }
                            Txt { width: parent.width; text: row.modelData.line; kind: "sm"; tone: "secondary"; lineHeight: 1.35 }
                        }
                        Pill {
                            id: rowPill
                            anchors.right: parent.right
                            y: 2
                            width: Math.min(implicitWidth, row.width * 0.42)
                            text: lab.shortText(row.modelData)
                            status: lab.statusOf(row.modelData)
                        }
                    }
                }
            }
        }
    }
    Rectangle {
        visible: !Theme.large
        x: list.width + Theme.sp4; y: list.y
        width: 1; height: list.height
        color: Theme.hair
    }

    // ---------------------------------------------------------------- the detail
    Flickable {
        id: detailArea
        anchors.top: header.bottom; anchors.topMargin: Theme.sp6
        anchors.bottom: parent.bottom
        x: Theme.large ? 0 : list.width + Theme.sp8
        width: parent.width - x
        visible: !Theme.large || lab.current !== null
        contentHeight: side.implicitHeight + Theme.sp3
        clip: true
        Column {
            id: side
            width: parent.width
            spacing: Theme.sp10

            Empty {
                visible: lab.current === null
                width: parent.width
                topPadding: Theme.sp8
                icon: "lab"
                title: T.labPick
                body: T.labPickBody
            }

            // ---- the chosen attack
            TaskCard {
                id: detailCard
                visible: lab.current !== null
                opacity: 1
                Behavior on opacity { NumberAnimation { duration: Theme.dur2 } }
                width: parent.width
                title: lab.current ? lab.current.title : ""
                Button { visible: Theme.large; kind: "quiet"; small: true; icon: "close"; text: T.close; onClicked: lab.chosen = "" }
                Txt { text: T.labTries; strong: true }
                Txt { width: parent.width; text: lab.current ? lab.current.tries : ""; tone: "secondary" }
                Item {
                    width: parent.width; height: 240 * Math.max(1, Theme.scale)
                    Surface { anchors.fill: parent; depth: 1; radius: Theme.rCard; padding: 0 }
                    AnimAttack { anchors.fill: parent; anchors.margins: Theme.sp3; record: lab.current; progress: lab.progress }
                }
                Txt { width: parent.width; text: T.labAttackerPicture; tone: "tertiary"; kind: "sm" }
                Item { visible: lab.current && lab.current.ran; width: 1; height: Theme.sp1 }
                Row {
                    visible: lab.current && lab.current.ran
                    spacing: Theme.sp3
                    Txt { text: T.labCheck; strong: true; anchors.verticalCenter: parent.verticalCenter }
                    Pill { text: lab.current ? lab.statusText(lab.current) : ""; status: lab.current ? lab.statusOf(lab.current) : "neutral"; anchors.verticalCenter: parent.verticalCenter }
                }
                Txt { visible: lab.current && lab.current.ran; width: parent.width
                      text: lab.current ? (lab.current.passed ? lab.current.caughtBy + ". " : "") + lab.current.verdict : "" }
                Item { width: 1; height: Theme.sp1 }
                Txt { text: T.labWithout; strong: true }
                Txt { width: parent.width; text: lab.current ? lab.current.without : ""; tone: "secondary" }
                Item { width: 1; height: Theme.sp1 }
                Flow { width: parent.width; spacing: Theme.sp2
                      PButton { primary: true; enabled: lab.current && !lab.current.running; busy: lab.current && lab.current.running === true
                                text: lab.current && lab.current.ran ? T.labRunAgain : T.labRun
                                onClicked: app.runAttack(lab.chosen) }
                      PButton { visible: lab.current && lab.current.ran; text: T.replay; onClicked: lab.replay() }
                      PButton { visible: lab.current && lab.current.ran; quiet: true; text: T.inspectorOpen; onClicked: lab.inspect(lab.current) } }
                Repeater {
                    model: lab.current && app.mode === "expert" ? lab.current.lines : []
                    Txt { required property string modelData; width: parent.width; text: modelData; kind: "mono"; tone: "tertiary" }
                }
            }

            // ---- policy R versus policy RE, side by side
            TaskCard {
                width: parent.width
                title: T.labCompareTitle
                summary: T.labCompareIntro
                Row {
                    width: parent.width
                    spacing: Theme.sp8
                    Repeater {
                        model: [{ name: T.labCompareR, note: T.labCompareRNote, safe: false, line: 1 },
                                { name: T.labCompareRE, note: T.labCompareRENote, safe: true, line: 2 }]
                        Item {
                            id: column
                            required property var modelData
                            required property int index
                            width: (parent.width - Theme.sp8) / 2
                            height: columnBody.implicitHeight
                            Rectangle { visible: column.index === 1; x: -Theme.sp4; width: 1; height: parent.height; color: Theme.hair }
                            Column {
                                id: columnBody
                                width: parent.width; spacing: Theme.sp2
                                Txt { text: column.modelData.name; kind: "lg"; width: parent.width }
                                Chip { maxWidth: parent.width; mark: column.modelData.safe ? "ok" : "fail"
                                       text: column.modelData.safe ? T.labOldLocked : T.labOldReadable }
                                Chip { maxWidth: parent.width; mark: "ok"; text: T.labNewLocked }
                                Txt { width: parent.width; visible: lab.collusion && lab.collusion.ran && lab.collusion.lines.length > column.modelData.line
                                      text: lab.collusion && lab.collusion.lines.length > column.modelData.line ? Theme.fmt(T.labMeasured, { line: lab.collusion.lines[column.modelData.line] }) : ""
                                      kind: "sm" }
                                Txt { width: parent.width; text: column.modelData.note; tone: "secondary"; kind: "sm" }
                            }
                        }
                    }
                }
                PButton { primary: lab.current === null; enabled: lab.collusion && !lab.collusion.running; busy: lab.collusion && lab.collusion.running === true
                          text: T.labCompareRun
                          onClicked: app.runAttack("collusion") }
            }
        }
    }

    // the travelling copy of the chosen row (shared element): a soft tint with the title
    Rectangle {
        id: ghost
        property string title: ""
        property string pending: ""
        property real toX: 0; property real toY: 0; property real toW: 0; property real toH: 0
        visible: false
        z: 20
        radius: Theme.rCard
        color: Theme.press
        Txt { x: Theme.sp3; y: Theme.sp3; text: ghost.title; kind: "lg"; wrapMode: Text.NoWrap }
    }
    SequentialAnimation {
        id: grow
        ScriptAction { script: { ghost.visible = true; ghost.opacity = 1; detailCard.opacity = 0 } }
        ParallelAnimation {
            NumberAnimation { target: ghost; property: "x"; to: ghost.toX; duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve }
            NumberAnimation { target: ghost; property: "y"; to: ghost.toY; duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve }
            NumberAnimation { target: ghost; property: "width"; to: ghost.toW; duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve }
            NumberAnimation { target: ghost; property: "height"; to: ghost.toH; duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve }
        }
        ScriptAction { script: { lab.chosen = ghost.pending; detailCard.opacity = 1 } }
        NumberAnimation { target: ghost; property: "opacity"; to: 0; duration: Theme.dur2 }
        ScriptAction { script: ghost.visible = false }
    }
}
