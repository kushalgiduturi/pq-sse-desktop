// The Quiet glass style guide (python -m app --styleguide): every token and component on one
// page, in one theme at a time. The window is the real layout: world, top bar (depth 3),
// one page panel (depth 2, pointer light) and the dock (depth 4). A band left of the panel
// shows the five depths side by side, with dense fills so the blur budget stays at three.
import QtQuick
import QtQuick.Effects
import QtQuick.Window

Window {
    id: win
    width: 1600
    height: 1000
    visible: true
    title: SG.windowTitle
    color: Theme.world

    property bool dark: true
    property bool reduceTransparency: false
    property bool reduceMotion: false
    property real textScale: 1.0
    property string current: "workspace"
    property int seg: 0
    property int tab: 0
    property var switches: [false, true]

    Binding { target: Theme; property: "dark"; value: win.dark }
    Binding { target: Theme; property: "reduceTransparency"; value: win.reduceTransparency }
    Binding { target: Theme; property: "reduceMotion"; value: win.reduceMotion }
    Binding { target: Theme; property: "scale"; value: win.textScale }
    Binding { target: Theme; property: "software"; value: GraphicsInfo.api === GraphicsInfo.Software }

    FontLoader { id: onest; source: Qt.resolvedUrl("../fonts/Onest-Variable.ttf") }
    FontLoader { id: stm; source: Qt.resolvedUrl("../fonts/ShareTechMono-Regular.ttf") }
    Binding { target: Theme; property: "ui"; value: onest.name; when: onest.status === FontLoader.Ready }
    Binding { target: Theme; property: "mono"; value: stm.name; when: stm.status === FontLoader.Ready }

    function scrollTo(y) { flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height)) }
    function scrollToSection(name) { var item = sectionItems[name]; if (item) scrollTo(item.mapToItem(page, 0, 0).y - Theme.sp2) }
    function openDialog() { dialog.show() }
    function showToast() { toast.show(SG.toast.text, "ok") }
    function closeOverlays() { dialog.open = false; toast.shown = false }
    readonly property var sectionItems: ({ "type": sType, "color": sColor, "buttons": sButtons, "fields": sFields,
                                           "choices": sChoices, "list": sList, "metrics": sMetrics, "status": sStatus,
                                           "empty": sEmpty, "stage": sStage, "overlays": sOverlays })
    readonly property real contentLength: flick.contentHeight

    // ---------------------------------------------------------------- depth 0 and its one blurred copy
    MultiEffect {
        id: worldBlur
        anchors.fill: world
        z: -1
        source: world
        autoPaddingEnabled: false
        blurEnabled: true
        blur: 1.0
        blurMax: Theme.worldBlur
    }
    World { id: world; anchors.fill: parent }
    Component.onCompleted: Theme.backdrop = worldBlur

    // ---------------------------------------------------------------- depth band, outside the panel
    Column {
        id: band
        visible: panel.x > 200
        x: Math.max(Theme.sp6, (panel.x - 150) / 2)
        anchors.verticalCenter: panel.verticalCenter
        spacing: Theme.sp5
        Repeater {
            model: SG.depths
            Column {
                id: dcell
                required property var modelData
                required property int index
                spacing: Theme.sp2
                Item {
                    width: 150; height: 64
                    Rectangle { visible: dcell.index === 0; anchors.fill: parent; radius: Theme.rCard; color: "transparent"; border.width: 1; border.color: Theme.worldInk }
                    Surface { visible: dcell.index > 0; anchors.fill: parent; depth: Math.max(1, dcell.index); blur: false
                              radius: dcell.index === 1 ? Theme.rCtl : dcell.index === 4 ? Theme.rFloat : Theme.rCard; padding: 0 }
                    Txt { anchors.centerIn: parent; text: dcell.modelData[0]; kind: "metric"; tone: "secondary"; font.family: Theme.ui }
                }
                Txt { width: 150; text: dcell.modelData[1]; kind: "sm"; strong: true; lineHeight: 1.2 }
            }
        }
    }

    // ---------------------------------------------------------------- top bar (depth 3)
    TopBar {
        id: bar
        x: Theme.barInset; y: Theme.barInset
        width: win.width - 2 * Theme.barInset
        story: SG.story
        engine: SG.engine
        engineStatus: "accent"
        themeLabel: SG.themeLabel
        searchLabel: SG.searchLabel
        searchKeys: SG.searchKeys
        onThemeClicked: win.dark = !win.dark
    }

    // ---------------------------------------------------------------- the page panel (depth 2)
    Surface {
        id: panel
        depth: 2
        pointerLight: true
        width: Math.min(Theme.pageMax, win.width - 2 * Theme.sp6)
        x: (win.width - width) / 2
        y: bar.y + bar.height + Theme.sp4
        height: dock.y - Theme.sp4 - y
        padding: 0
        Flickable {
            id: flick
            objectName: "sgFlick"
            anchors.fill: parent
            anchors.margins: Theme.sp10
            anchors.rightMargin: Theme.sp10 - 8
            contentWidth: width - 8
            contentHeight: page.implicitHeight + Theme.sp16
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            Column {
                id: page
                width: flick.contentWidth
                spacing: Theme.sp12

                // ---------------- title
                Column {
                    width: parent.width
                    spacing: Theme.sp3
                    Txt { text: SG.title; kind: "display" }
                    Txt { width: Math.min(parent.width, 640); text: SG.intro; tone: "secondary" }
                }

                // ---------------- type
                Column {
                    id: sType
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.type }
                    Repeater {
                        model: [["display", SG.type.display], ["xl", SG.type.xl], ["lg", SG.type.lg], ["md", SG.type.md],
                                ["sm", SG.type.sm], ["xs", SG.type.xs], ["mono", SG.type.mono]]
                        Row {
                            id: trow
                            required property var modelData
                            required property int index
                            width: page.width
                            spacing: Theme.sp6
                            Txt { width: 140; text: SG.type.scale[trow.index]; kind: "sm"; tone: "tertiary"; anchors.baseline: sample.baseline }
                            Txt { id: sample; width: parent.width - 164; text: trow.modelData[1]; kind: trow.modelData[0]
                                  tone: trow.modelData[0] === "sm" || trow.modelData[0] === "xs" ? "secondary" : "primary" }
                        }
                    }
                    Txt { text: SG.type.monoNote; kind: "sm"; tone: "secondary" }
                }

                // ---------------- color
                Column {
                    id: sColor
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.color }
                    Flow {
                        width: parent.width
                        spacing: Theme.sp6
                        Repeater {
                            model: [Theme.accent, Theme.accentText, Theme.text, Theme.text2, Theme.text3, Theme.ok, Theme.warn, Theme.bad, Theme.info]
                            Column {
                                id: sw
                                required property color modelData
                                required property int index
                                spacing: Theme.sp2
                                width: 104
                                Rectangle { width: 104; height: 56; radius: Theme.rSm; color: sw.modelData; border.width: 1; border.color: Theme.hair }
                                Txt { text: SG.colors[sw.index]; kind: "sm"; strong: true; lineHeight: 1.2 }
                                Txt { text: String(sw.modelData).toUpperCase(); kind: "mono"; tone: "secondary"; lineHeight: 1.2 }
                            }
                        }
                    }
                }

                // ---------------- depth
                Column {
                    width: parent.width; spacing: Theme.sp4
                    SectionTitle { text: SG.sections.depth }
                    Repeater {
                        model: SG.depths
                        ListRow {
                            id: drow
                            required property var modelData
                            width: page.width
                            Row {
                                spacing: Theme.sp6
                                Txt { width: 40; text: drow.modelData[0]; kind: "mono"; tone: "tertiary" }
                                Txt { width: 180; text: drow.modelData[1]; strong: true }
                                Txt { width: page.width - 268; text: drow.modelData[2]; tone: "secondary" }
                            }
                        }
                    }
                    Txt { width: parent.width; text: SG.depthNote; kind: "sm"; tone: "secondary" }
                }

                // ---------------- buttons
                Column {
                    id: sButtons
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.buttons }
                    Flow {
                        width: parent.width; spacing: Theme.sp3
                        Button { kind: "primary"; text: SG.buttons.primary; icon: "lock" }
                        Button { kind: "secondary"; text: SG.buttons.secondary; icon: "plus" }
                        Button { kind: "ghost"; text: SG.buttons.ghost }
                        Button { kind: "danger"; text: SG.buttons.danger }
                        Button { kind: "primary"; text: SG.buttons.loading; loading: true }
                        Button { kind: "secondary"; text: SG.buttons.disabled; enabled: false }
                    }
                    Txt { width: parent.width; text: SG.buttons.note; kind: "sm"; tone: "secondary" }
                }

                // ---------------- fields
                Row {
                    id: sFields
                    width: parent.width; spacing: Theme.sp8
                    Column {
                        width: (parent.width - Theme.sp8) / 2; spacing: Theme.sp5
                        SectionTitle { text: SG.sections.fields }
                        Field { width: parent.width; label: SG.fields.label; hint: SG.fields.hint; help: SG.fields.help }
                        Field { width: parent.width; label: SG.fields.errLabel; hint: SG.fields.errHint; error: SG.fields.error
                                secret: true; text: SG.fields.errValue }
                    }
                    Column {
                        id: sChoices
                        width: (parent.width - Theme.sp8) / 2; spacing: Theme.sp5
                        SectionTitle { text: SG.sections.choices }
                        Segmented { width: 280; labels: SG.segmented; name: SG.segmentedName; current: win.seg; onChosen: (i) => win.seg = i }
                        Tabs { labels: SG.tabs; name: SG.tabsName; current: win.tab; onChosen: (i) => win.tab = i }
                        Repeater {
                            model: SG.switches
                            Switch {
                                id: swi
                                required property var modelData
                                required property int index
                                width: parent.width
                                text: modelData[0]; help: modelData[1]
                                checked: win.switches[index]
                                onToggled: (on) => { var s = win.switches.slice(); s[swi.index] = on; win.switches = s }
                            }
                        }
                    }
                }

                // ---------------- list and table
                Column {
                    id: sList
                    width: parent.width; spacing: 0
                    SectionTitle { text: SG.sections.list; count: String(SG.table.rows.length) }
                    readonly property var cols: [0.42, 0.16, 0.2, 0.22]
                    ListRow {
                        width: parent.width; padY: Theme.sp2
                        Row {
                            Repeater {
                                model: SG.table.head
                                Txt { required property string modelData; required property int index
                                      width: page.width * sList.cols[index]; text: modelData; kind: "xs"; tone: "tertiary"; strong: true }
                            }
                        }
                    }
                    Repeater {
                        model: SG.table.rows
                        ListRow {
                            id: lrow
                            required property var modelData
                            required property int index
                            width: page.width
                            clickable: true
                            selected: index === 0
                            Row {
                                anchors.verticalCenter: parent.verticalCenter
                                Row {
                                    width: page.width * sList.cols[0]; spacing: Theme.sp3
                                    Icon { name: "document"; size: 18; color: Theme.text2; anchors.verticalCenter: parent.verticalCenter }
                                    Txt { text: lrow.modelData[0]; anchors.verticalCenter: parent.verticalCenter; wrapMode: Text.NoWrap }
                                }
                                Txt { width: page.width * sList.cols[1]; text: lrow.modelData[1]; kind: "mono"; tone: "secondary"; anchors.verticalCenter: parent.verticalCenter }
                                Txt { width: page.width * sList.cols[2]; text: lrow.modelData[2]; tone: "secondary"; anchors.verticalCenter: parent.verticalCenter }
                                Item { width: page.width * sList.cols[3]; height: pill.height; anchors.verticalCenter: parent.verticalCenter
                                       Pill { id: pill; text: lrow.modelData[3]; status: lrow.modelData[4] } }
                            }
                        }
                    }
                }

                // ---------------- metrics and status
                Column {
                    id: sMetrics
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.metrics }
                    Metrics { width: parent.width; items: SG.metrics }
                }
                Column {
                    id: sStatus
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.status }
                    Flow {
                        width: parent.width; spacing: Theme.sp3
                        Repeater { model: SG.pills; Pill { required property var modelData; text: modelData[0]; status: modelData[1] } }
                    }
                    Txt { text: SG.pillNote; kind: "sm"; tone: "secondary" }
                }

                // ---------------- empty state and stage
                Row {
                    width: parent.width; spacing: Theme.sp8
                    Column {
                        id: sEmpty
                        width: (parent.width - Theme.sp8) / 2; spacing: Theme.sp8
                        SectionTitle { text: SG.sections.empty }
                        Empty { width: parent.width; title: SG.empty.title; body: SG.empty.body; action: SG.empty.action }
                    }
                    Column {
                        id: sStage
                        width: (parent.width - Theme.sp8) / 2; spacing: Theme.sp8
                        SectionTitle { text: SG.sections.stage }
                        Row {
                            anchors.horizontalCenter: parent.horizontalCenter
                            spacing: Theme.sp12
                            Repeater {
                                model: SG.figures
                                Figure { required property var modelData; required property int index
                                         name: modelData[0]; role: modelData[1]; glyph: modelData[2]; active: index === 0 }
                            }
                        }
                        Txt { width: parent.width; text: SG.stageNote; kind: "sm"; tone: "secondary" }
                    }
                }

                // ---------------- overlays
                Column {
                    id: sOverlays
                    width: parent.width; spacing: Theme.sp5
                    SectionTitle { text: SG.sections.overlays }
                    Row {
                        spacing: Theme.sp3
                        Button { kind: "secondary"; text: SG.dialog.open; onClicked: win.openDialog() }
                        Button { kind: "secondary"; text: SG.toast.open; onClicked: win.showToast() }
                    }
                }
            }
        }
    }

    // ---------------------------------------------------------------- dock (depth 4) and toast
    Dock {
        id: dock
        items: SG.dock
        current: win.current
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height - height - Theme.barInset
        onChosen: (key) => win.current = key
    }
    Toast {
        id: toast
        action: SG.toast.action
        anchors.horizontalCenter: parent.horizontalCenter
        y: dock.y - height - Theme.sp4
        z: 50
    }
    Dialog {
        id: dialog
        title: SG.dialog.title
        body: SG.dialog.body
        Button { kind: "danger"; text: SG.dialog.confirm; onClicked: dialog.hide() }
        Button { kind: "ghost"; text: SG.dialog.cancel; onClicked: dialog.hide() }
    }
}
