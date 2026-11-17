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
    color: Theme.world
    title: T.appName + ": search locked files without unlocking them"

    property string page: app.mode === "expert" ? "workspace" : "journey"
    property bool inspectorOpen: false
    property int inspectIndex: -1
    readonly property var pages: ["journey", "stage", "workspace", "lab", "insights"]
    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    readonly property real inspectorWidth: Math.min(500, width * 0.36)
    // A modal layer is open: everything behind it is disabled, so Tab cannot leave it,
    // and the control that had the focus gets it back when the layer closes.
    readonly property bool modalOpen: palette.open || errorSheet.open || glossarySheet.open || welcomeSheet.open
    property var focusBefore: null
    onModalOpenChanged: {
        if (modalOpen) {
            if (!focusBefore) focusBefore = win.activeFocusItem
        } else {
            var item = focusBefore
            focusBefore = null
            // after this change has re-enabled the layers behind the closed one
            Qt.callLater(function () { if (item && item.visible && item.enabled) item.forceActiveFocus() })
        }
    }
    // Keyboard focus moved: scroll every scrolling area that holds the focused control so it is visible.
    onActiveFocusItemChanged: ensureVisible(activeFocusItem)
    function ensureVisible(item) {
        if (!item) return
        for (var p = item.parent; p; p = p.parent) {
            if (p.contentItem !== undefined && p.contentY !== undefined && p.flickableDirection !== undefined) {
                var top = item.mapToItem(p.contentItem, 0, 0).y
                var bottom = top + item.height
                var margin = 16
                if (top - margin < p.contentY) p.contentY = Math.max(0, top - margin)
                else if (bottom + margin > p.contentY + p.height)
                    p.contentY = Math.min(Math.max(0, p.contentHeight - p.height), bottom + margin - p.height)
            }
        }
    }

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
    Binding { target: Theme; property: "reduceTransparency"; value: platform.reduceTransparency }
    Binding { target: Theme; property: "touch"; value: platform.touch }
    FontLoader { id: onest; source: Qt.resolvedUrl("../fonts/Onest-Variable.ttf") }
    FontLoader { id: stm; source: Qt.resolvedUrl("../fonts/ShareTechMono-Regular.ttf") }
    Binding { target: Theme; property: "ui"; value: onest.name; when: onest.status === FontLoader.Ready }
    Binding { target: Theme; property: "mono"; value: stm.name; when: stm.status === FontLoader.Ready }
    Component.onCompleted: {
        app.setSoftware(win.software)
        Theme.backdrop = win.software ? null : blurredRoom
    }

    // ------------------------------------------------------------------ depth 0: the world, and its one blurred copy
    // Glass at depth 2 to 4 samples the copy instead of blurring itself (one blur pass, Theme.worldBlur).
    MultiEffect {
        id: blurredRoom
        anchors.fill: room
        z: -1                              // under the world: seen only through the glass that samples it
        source: room
        autoPaddingEnabled: false
        blurEnabled: true; blur: 1.0; blurMax: Theme.worldBlur
    }
    World { id: room; anchors.fill: parent; scene: false }

    // ------------------------------------------------------------------ content layer: pages
    // The one page panel (depth 2): centered, at most Theme.pageMax wide, narrower while the
    // inspector drawer is open. Pages are flat inside it.
    readonly property real availableWidth: win.width - 2 * Theme.barInset - (win.inspectorOpen ? win.inspectorWidth + Theme.sp4 : 0)
    Surface {
        id: panel
        depth: 2
        pointerLight: true
        padding: 0
        y: storyBar.y + storyBar.height + Theme.sp4
        height: dock.y - Theme.sp4 - y
        width: Math.min(Theme.pageMax, win.availableWidth)
        x: Theme.barInset + (win.availableWidth - width) / 2
        track: x + width
        Behavior on x { NumberAnimation { duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
        Behavior on width { NumberAnimation { duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
    }
    Item {
        id: host
        enabled: !win.modalOpen
        x: panel.x + Theme.sp8; y: panel.y + Theme.sp6
        width: panel.width - 2 * Theme.sp8
        height: panel.height - Theme.sp6 - Theme.sp4

        component Page: Item {
            id: pg
            property string key: ""
            readonly property int order: win.pages.indexOf(key)
            readonly property bool current: win.page === key
            anchors.fill: parent
            opacity: current ? 1 : 0
            visible: opacity > 0.01
            enabled: current
            // page change: a short fade with an 8 px slide in the direction of travel (none with Reduce motion)
            transform: Translate {
                x: pg.current || Theme.reduceMotion ? 0 : (win.pages.indexOf(win.page) > pg.order ? -8 : 8)
                Behavior on x { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
            }
            Behavior on opacity { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
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
        enabled: !win.modalOpen
        x: Theme.barInset; y: Theme.barInset
        width: win.width - 2 * Theme.barInset
        onOpenPalette: palette.show()
        onOpenInsights: win.go("insights")
        onOpenWorkspaceCloud: { app.setRole("cloud"); win.go("workspace") }
        onOpenInspector: win.inspect(events.count - 1)
    }
    Dock {
        id: dock
        enabled: !win.modalOpen
        items: DEST.map(function (d) { return { key: d.key, icon: d.key, label: d.label } })
        labelsOnly: Theme.large
        blur: !win.inspectorOpen           // at most three blurred layers: the open inspector takes the dock's
        anchors.horizontalCenter: parent.horizontalCenter
        y: win.height - height - Theme.barInset
        current: win.page
        onChosen: (key) => win.go(key)
    }
    Button {
        enabled: !win.modalOpen
        kind: "secondary"
        icon: "inspect"
        anchors.right: parent.right; anchors.rightMargin: Theme.barInset + Theme.sp2
        anchors.verticalCenter: dock.verticalCenter
        visible: !win.inspectorOpen && !Theme.large && x > dock.x + dock.width + Theme.sp4
        text: T.inspectorOpen
        onClicked: win.inspect(events.count - 1)
        Accessible.description: T.inspectorOpenHint
    }
    Inspector {
        id: inspector
        enabled: !win.modalOpen
        width: win.inspectorWidth
        anchors.top: storyBar.bottom; anchors.topMargin: Theme.sp4
        anchors.bottom: dock.top; anchors.bottomMargin: Theme.sp4
        x: win.inspectorOpen ? win.width - width - Theme.barInset : win.width + 40
        track: x
        opacity: win.inspectorOpen ? 1 : 0
        visible: opacity > 0.01
        index: win.inspectIndex
        onClose: win.inspectorOpen = false
        onJump: (i) => win.inspect(i)
        Behavior on x { NumberAnimation { duration: Theme.dur4; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
        Behavior on opacity { NumberAnimation { duration: Theme.dur2 } }
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
