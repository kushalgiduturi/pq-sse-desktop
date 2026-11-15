// PQ-SSE Desktop, spatial UI: the room, the Story bar, five pages, the dock, the Step
// Inspector, the command palette and the sheets.
import QtQuick
import QtQuick.Effects
import QtQuick.Window

Window {
    id: win
    width: 1440
    height: 900
    minimumWidth: 1120
    minimumHeight: 720
    visible: true
    color: Theme.roomTop
    title: T.appName + ": search locked files without unlocking them"

    property string page: app.mode === "expert" ? "workspace" : "journey"
    property bool inspectorOpen: false
    property int inspectIndex: -1
    property real mx: 0.5
    property real my: 0.5
    readonly property var pages: ["journey", "stage", "workspace", "lab", "insights"]
    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    readonly property real inspectorWidth: Math.min(500, width * 0.36)

    function go(key) { if (pages.indexOf(key) >= 0) page = key }
    function inspect(index) {
        inspector.override = null
        if (events.count === 0) { inspectIndex = -1; inspectorOpen = true; return }
        inspectIndex = Math.max(0, Math.min(events.count - 1, index))
        inspectorOpen = true
    }
    function showError(e) {
        errorSheet.title = e.what
        errorSheet.rows = [{ head: T.errorWhy, body: e.why }, { head: T.errorNext, body: e.next }]
        errorSheet.technical = e.technical
        errorSheet.show()
    }
    function showGlossary(g) {
        if (!g.name) return
        glossarySheet.title = g.name
        var rows = [{ head: "", body: g.plain }, { head: "", body: g.more }]
        if (g.simplification) rows.push({ head: T.simplification, body: g.simplification })
        glossarySheet.rows = rows
        glossarySheet.show()
    }

    Binding { target: Theme; property: "dark"; value: app.dark }
    Binding { target: Theme; property: "reduceMotion"; value: app.reduceMotion }
    Binding { target: Theme; property: "software"; value: win.software }
    Binding { target: Theme; property: "scale"; value: app.textScale }
    Component.onCompleted: {
        app.setSoftware(win.software)
        var families = Qt.fontFamilies()
        Theme.fontFamily = families.indexOf("Segoe UI Variable") >= 0 ? "Segoe UI Variable" : "Segoe UI"
        Theme.monoFamily = families.indexOf("Cascadia Mono") >= 0 ? "Cascadia Mono" : "Consolas"
        Theme.backdrop = win.software ? null : blurredRoom
    }

    // ------------------------------------------------------------------ background layer
    Item {
        id: room
        anchors.fill: parent
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Theme.roomTop }
                GradientStop { position: 1.0; color: Theme.roomBottom }
            }
        }
        Repeater {
            model: [{ c: Theme.accent, x: 0.14, y: 0.20, s: 0.55 }, { c: Theme.carol, x: 0.86, y: 0.12, s: 0.48 },
                    { c: Theme.bob, x: 0.56, y: 0.92, s: 0.60 }]
            Rectangle {
                id: light
                required property var modelData
                required property int index
                property real drift: 0
                visible: !win.software
                width: win.width * modelData.s; height: width; radius: width / 2
                opacity: Theme.dark ? 0.16 : 0.22
                x: win.width * modelData.x - width / 2 + drift * 50 - (win.mx - 0.5) * 30
                y: win.height * modelData.y - height / 2 + (1 - drift) * 36 - (win.my - 0.5) * 22
                gradient: Gradient {
                    GradientStop { position: 0.0; color: light.modelData.c }
                    GradientStop { position: 1.0; color: Theme.tint(light.modelData.c, 0.0) }
                }
                SequentialAnimation on drift {
                    running: !Theme.reduceMotion && win.active
                    loops: Animation.Infinite
                    NumberAnimation { to: 1; duration: 11000 + light.index * 3000; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 0; duration: 11000 + light.index * 3000; easing.type: Easing.InOutSine }
                }
            }
        }
    }
    // One blurred copy of the room. Floating glass panels sample it instead of blurring themselves.
    ShaderEffectSource { id: roomCopy; sourceItem: room; visible: false; live: !win.software; textureSize: Qt.size(win.width / 2, win.height / 2) }
    MultiEffect {
        id: blurredRoom
        anchors.fill: parent
        source: roomCopy
        visible: false                     // drawn only through the panels that sample it
        blurEnabled: true; blur: 1.0; blurMax: 48
    }
    MouseArea {
        anchors.fill: parent
        hoverEnabled: !Theme.reduceMotion
        acceptedButtons: Qt.NoButton
        onPositionChanged: (mouse) => { win.mx = mouse.x / width; win.my = mouse.y / height }
    }

    // ------------------------------------------------------------------ content layer: pages
    Item {
        id: host
        anchors.top: storyBar.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: dock.top; anchors.bottomMargin: Theme.s16
        anchors.left: parent.left; anchors.leftMargin: Theme.s32
        anchors.right: parent.right
        anchors.rightMargin: win.inspectorOpen ? win.inspectorWidth + Theme.s32 + Theme.s16 : Theme.s32
        Behavior on anchors.rightMargin { NumberAnimation { duration: Theme.moveSlow; easing.type: Easing.OutCubic } }

        component Page: Item {
            id: pg
            property string key: ""
            readonly property int order: win.pages.indexOf(key)
            readonly property bool current: win.page === key
            anchors.fill: parent
            opacity: current ? 1 : 0
            visible: opacity > 0.01
            enabled: current
            scale: current || Theme.reduceMotion ? 1 : (win.pages.indexOf(win.page) > order ? 0.94 : 1.05)
            transform: Translate { x: Theme.reduceMotion ? 0 : (win.mx - 0.5) * 8; y: Theme.reduceMotion ? 0 : (win.my - 0.5) * 6 }
            Behavior on opacity { NumberAnimation { duration: Theme.reduceMotion ? Theme.base : Theme.slow; easing.type: Easing.OutCubic } }
            Behavior on scale { enabled: !Theme.reduceMotion; SpringAnimation { spring: Theme.spring; damping: Theme.damping; epsilon: 0.002 } }
        }
        Page { key: "journey"; PageJourney { anchors.fill: parent; onInspect: (i) => win.inspect(i) } }
        Page { key: "stage"; PageStage { anchors.fill: parent; active: win.page === "stage"; onInspect: (i) => win.inspect(i) } }
        Page { key: "workspace"; PageWorkspace { anchors.fill: parent; onInspect: (i) => win.inspect(i) } }
        Page { key: "lab"; PageLab { anchors.fill: parent; onInspect: (record) => { inspector.override = record; win.inspectorOpen = true } } }
        Page { key: "insights"; PageInsights { anchors.fill: parent } }
    }

    // ------------------------------------------------------------------ floating layer
    StoryBar {
        id: storyBar
        anchors.top: parent.top; anchors.topMargin: Theme.s16
        anchors.left: parent.left; anchors.leftMargin: Theme.s24
        anchors.right: parent.right; anchors.rightMargin: Theme.s24
        onOpenPalette: palette.show()
        onOpenInsights: win.go("insights")
        onOpenWorkspaceCloud: { app.setRole("cloud"); win.go("workspace") }
    }
    Dock {
        id: dock
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.s16
        current: win.page
        onChosen: (key) => win.go(key)
    }
    PButton {
        anchors.right: parent.right; anchors.rightMargin: Theme.s24
        anchors.verticalCenter: dock.verticalCenter
        visible: !win.inspectorOpen
        text: T.inspectorOpen
        onClicked: win.inspect(events.count - 1)
        Accessible.description: T.inspectorOpenHint
    }
    Inspector {
        id: inspector
        width: win.inspectorWidth
        anchors.top: storyBar.bottom; anchors.topMargin: Theme.s16
        anchors.bottom: dock.top; anchors.bottomMargin: Theme.s16
        x: win.inspectorOpen ? win.width - width - Theme.s24 : win.width + 40
        track: x
        opacity: win.inspectorOpen ? 1 : 0
        visible: opacity > 0.01
        index: win.inspectIndex
        onClose: win.inspectorOpen = false
        onJump: (i) => win.inspect(i)
        Behavior on x { NumberAnimation { duration: Theme.moveSlow; easing.type: Easing.OutCubic } }
        Behavior on opacity { NumberAnimation { duration: Theme.base } }
    }
    CommandPalette { id: palette; z: 10 }
    Sheet { id: errorSheet; z: 11; error: true }
    Sheet { id: glossarySheet; z: 11 }
    Sheet {
        id: welcomeSheet
        z: 12
        title: T.welcomeTitle
        rows: [{ head: "", body: T.welcomeIdea }, { head: "", body: T.welcomeCast }, { head: "", body: T.welcomeHow }, { head: "", body: T.welcomeHonest }]
        actionText: T.welcomeStart
        closeText: T.welcomeLater
        onAction: app.dismissWelcome(true)
        onDismissed: app.dismissWelcome(false)
    }
    Timer { interval: 400; running: app.showWelcome; onTriggered: welcomeSheet.show() }

    // ------------------------------------------------------------------ keys and signals
    Shortcut { sequence: "Ctrl+K"; onActivated: palette.open ? palette.hide() : palette.show() }
    Shortcut { sequence: "F1"; onActivated: palette.show() }
    Shortcut { sequences: ["Ctrl+1", "Alt+1"]; onActivated: win.go("journey") }
    Shortcut { sequences: ["Ctrl+2", "Alt+2"]; onActivated: win.go("stage") }
    Shortcut { sequences: ["Ctrl+3", "Alt+3"]; onActivated: win.go("workspace") }
    Shortcut { sequences: ["Ctrl+4", "Alt+4"]; onActivated: win.go("lab") }
    Shortcut { sequences: ["Ctrl+5", "Alt+5"]; onActivated: win.go("insights") }
    Shortcut { sequence: "Ctrl+I"; onActivated: win.inspectorOpen ? win.inspectorOpen = false : win.inspect(events.count - 1) }
    Shortcut { sequence: "Escape"; enabled: win.inspectorOpen && !palette.open && !errorSheet.open && !glossarySheet.open; onActivated: win.inspectorOpen = false }
    Item {
        // Plain number keys 1 to 5 and the letter I, unless a text field has the focus.
        focus: true
        Keys.onPressed: (event) => {
            if (event.key >= Qt.Key_1 && event.key <= Qt.Key_5) { win.go(win.pages[event.key - Qt.Key_1]); event.accepted = true }
            else if (event.key === Qt.Key_I) { win.inspect(events.count - 1); event.accepted = true }
        }
    }
    Connections {
        target: app
        function onNavigate(key) { win.go(key) }
        function onFailed(e) { win.showError(e) }
        function onGlossaryRequested(g) { win.showGlossary(g) }
        function onInspectRequested(i) { win.inspect(i) }
        function onWelcomeRequested() { welcomeSheet.show() }
    }
}
