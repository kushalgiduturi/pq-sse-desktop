// Milestone 0 spike: is Qt Quick good enough for the spatial UI?
// A room background with moving light, a glass panel, a floating dock, a depth page
// transition and an encryption scramble animation that replays a real AES-256-GCM event.
// With the software renderer (no GPU) blur and shadows are replaced by flat tints.
import QtQuick
import QtQuick.Effects
import QtQuick.Window

Window {
    id: win
    width: 1280
    height: 800
    visible: true
    color: "#0e1420"
    title: "PQ-SSE Desktop: Qt Quick spike"

    readonly property bool software: GraphicsInfo.api === GraphicsInfo.Software
    readonly property bool reduceMotion: spike.reduceMotion
    property int page: 0
    property real mx: 0.5
    property real my: 0.5

    // Motion tokens (the only durations and curves the real UI will use).
    readonly property int dFast: 120
    readonly property int dBase: 220
    readonly property int dSlow: 360
    readonly property int dStage: 600

    function showPage(index) { page = index }

    // ------------------------------------------------------------------ background room
    Item {
        id: room
        anchors.fill: parent
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#101a2e" }
                GradientStop { position: 0.55; color: "#1b2c4a" }
                GradientStop { position: 1.0; color: "#32507a" }
            }
        }
        Repeater {
            model: [{ c: "#5b8cff", x: 0.18, y: 0.30, s: 520 }, { c: "#b06cff", x: 0.78, y: 0.22, s: 460 },
                    { c: "#3ed6c0", x: 0.55, y: 0.85, s: 600 }]
            Rectangle {
                required property var modelData
                required property int index
                width: modelData.s; height: modelData.s; radius: width / 2
                opacity: 0.30
                x: win.width * modelData.x - width / 2 + drift * 60 + (win.mx - 0.5) * -40
                y: win.height * modelData.y - height / 2 + (1 - drift) * 40 + (win.my - 0.5) * -30
                property real drift: 0
                gradient: Gradient {
                    GradientStop { position: 0.0; color: modelData.c }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                SequentialAnimation on drift {
                    running: !win.reduceMotion
                    loops: Animation.Infinite
                    NumberAnimation { to: 1; duration: 9000 + index * 2500; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 0; duration: 9000 + index * 2500; easing.type: Easing.InOutSine }
                }
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        onPositionChanged: (mouse) => { win.mx = mouse.x / width; win.my = mouse.y / height }
    }

    // ------------------------------------------------------------------ glass panel
    component Glass: Item {
        id: glass
        default property alias content: inner.data
        property real radius: 28
        ShaderEffectSource {
            id: grab
            anchors.fill: parent
            sourceItem: room
            sourceRect: Qt.rect(glass.mapToItem(room, 0, 0).x, glass.mapToItem(room, 0, 0).y, glass.width, glass.height)
            visible: false
            live: !win.software
        }
        Rectangle { id: maskShape; anchors.fill: parent; radius: glass.radius; visible: false; layer.enabled: true }
        MultiEffect {
            visible: !win.software
            anchors.fill: parent
            source: grab
            blurEnabled: true
            blur: 1.0
            blurMax: 48
            saturation: 0.25
            maskEnabled: true
            maskSource: maskShape
        }
        Rectangle {
            anchors.fill: parent
            radius: glass.radius
            color: win.software ? "#2a3b5c" : "#33ffffff"
            border.width: 1
            border.color: "#55ffffff"
        }
        Rectangle {
            visible: !win.software
            z: -1
            anchors.fill: parent
            anchors.topMargin: 18
            radius: glass.radius
            color: "#000000"
            opacity: 0.35
            layer.enabled: true
            layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 40 }
        }
        Item { id: inner; anchors.fill: parent; anchors.margins: 28 }
    }

    // ------------------------------------------------------------------ pages with depth transition
    component Page: Item {
        id: pg
        property int index: 0
        readonly property bool current: win.page === index
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -40
        width: Math.min(parent.width - 160, 980)
        height: Math.min(parent.height - 240, 520)
        opacity: current ? 1 : 0
        scale: current ? 1 : (win.page > index ? 0.88 : 1.08)
        visible: opacity > 0.01
        transform: Translate { x: (win.mx - 0.5) * 14; y: (win.my - 0.5) * 10 + (pg.current ? 0 : 30) }
        Behavior on opacity { NumberAnimation { duration: win.reduceMotion ? win.dBase : win.dSlow; easing.type: Easing.OutCubic } }
        Behavior on scale {
            enabled: !win.reduceMotion
            SpringAnimation { spring: 3.2; damping: 0.36; epsilon: 0.002 }
        }
    }

    Page {
        index: 0
        Glass {
            anchors.fill: parent
            Column {
                anchors.fill: parent
                spacing: 18
                Text { text: "Alice locks a document"; color: "white"; font.pixelSize: 30; font.weight: Font.DemiBold }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    color: "#d6e2f5"; font.pixelSize: 16
                    text: enc.caption
                }
                Item { width: 1; height: 16 }
                // The scramble: each letter flips into a ciphertext glyph as the lock passes over it.
                Item {
                    id: enc
                    width: parent.width
                    height: 150
                    property string plain: "Invoice 1042, MRI scanner"
                    property string cipher: ""
                    property string caption: "Press Space, or wait: the app encrypts for real, then replays it slowly."
                    property real progress: 0
                    readonly property real cell: Math.min(34, width / Math.max(1, plain.length))
                    Row {
                        id: letters
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: enc.plain.length
                            Item {
                                id: cellItem
                                required property int index
                                width: enc.cell; height: 56
                                readonly property real p: Math.max(0, Math.min(1, enc.progress * (enc.plain.length + 4) - index))
                                Rectangle {
                                    anchors.fill: parent; anchors.margins: 2; radius: 8
                                    color: parent.p > 0.5 ? "#3a1f6feb" : "#22ffffff"
                                    border.width: 1; border.color: parent.p > 0.5 ? "#7fa8ff" : "#44ffffff"
                                }
                                Text {
                                    anchors.centerIn: parent
                                    text: parent.p > 0.5 ? enc.cipher.charAt(index % Math.max(1, enc.cipher.length)) : enc.plain.charAt(index)
                                    color: parent.p > 0.5 ? "#9ec1ff" : "white"
                                    font.pixelSize: 22
                                    font.family: parent.p > 0.5 ? "Consolas" : "Segoe UI"
                                    transform: Rotation {
                                        origin.x: enc.cell / 2 - 6; origin.y: 14
                                        axis { x: 1; y: 0; z: 0 }
                                        angle: win.reduceMotion ? 0 : (cellItem.p < 0.5 ? cellItem.p * 180 : (1 - cellItem.p) * 180)
                                    }
                                }
                            }
                        }
                    }
                    // Padlock (a metaphor for AES-256-GCM, labeled as such in the caption).
                    Item {
                        width: 54; height: 70
                        x: Math.min(letters.width, enc.progress * (enc.plain.length + 4) * enc.cell) - 10
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.verticalCenterOffset: -4
                        Rectangle {
                            x: 12; y: enc.progress >= 1 ? 8 : 0; width: 30; height: 34; radius: 15
                            color: "transparent"; border.width: 6; border.color: "#ffd166"
                            Behavior on y { NumberAnimation { duration: win.dBase; easing.type: Easing.OutBack } }
                        }
                        Rectangle { x: 4; y: 28; width: 46; height: 38; radius: 9; color: "#ffd166" }
                        Rectangle { x: 24; y: 40; width: 6; height: 14; radius: 3; color: "#3a2a00" }
                    }
                    NumberAnimation on progress {
                        id: replay
                        running: false
                        from: 0; to: 1
                        duration: win.reduceMotion ? 1 : 2600
                        easing.type: Easing.InOutQuad
                    }
                }
                Row {
                    spacing: 10
                    opacity: enc.progress >= 1 ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: win.dBase } }
                    Repeater {
                        model: spike.tags
                        Rectangle {
                            required property string modelData
                            height: 30; width: label.implicitWidth + 24; radius: 15
                            color: "#2238d9a9"; border.width: 1; border.color: "#6638d9a9"
                            Text { id: label; anchors.centerIn: parent; text: parent.modelData; color: "#c8fff0"; font.pixelSize: 13 }
                        }
                    }
                }
            }
        }
    }

    Page {
        index: 1
        Glass {
            anchors.fill: parent
            Column {
                anchors.centerIn: parent
                spacing: 14
                Text { text: "Second page"; color: "white"; font.pixelSize: 30; font.weight: Font.DemiBold; anchors.horizontalCenter: parent.horizontalCenter }
                Text {
                    text: "The page before receded and faded. This one rose into focus with a spring."
                    color: "#d6e2f5"; font.pixelSize: 16
                }
                Text {
                    text: "Renderer: " + (win.software ? "software (no GPU): blur and shadows are off" : "GPU scene graph: blur and shadows are on")
                    color: "#ffd166"; font.pixelSize: 16
                }
            }
        }
    }

    // ------------------------------------------------------------------ floating dock
    Glass {
        id: dock
        radius: 30
        width: dockRow.implicitWidth + 56
        height: 96
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 26
        Row {
            id: dockRow
            anchors.centerIn: parent
            spacing: 14
            Repeater {
                model: ["Journey", "Stage", "Workspace", "Security Lab", "Insights"]
                Item {
                    id: dockItem
                    required property string modelData
                    required property int index
                    width: 92; height: 60
                    readonly property bool active: win.page === index % 2
                    scale: hover.hovered ? 1.18 : 1.0
                    Behavior on scale { enabled: !win.reduceMotion; SpringAnimation { spring: 5; damping: 0.4 } }
                    HoverHandler { id: hover }
                    TapHandler { onTapped: win.showPage(dockItem.index % 2) }
                    Rectangle {
                        width: 34; height: 34; radius: 11
                        anchors.horizontalCenter: parent.horizontalCenter
                        color: dockItem.active && dockItem.index < 2 ? "#5b8cff" : "#44ffffff"
                        Text { anchors.centerIn: parent; text: dockItem.index + 1; color: "white"; font.pixelSize: 15; font.weight: Font.DemiBold }
                    }
                    Text {
                        anchors.bottom: parent.bottom
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: dockItem.modelData; color: "white"; font.pixelSize: 12
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------ wiring to Python
    Connections {
        target: spike
        function onEncrypted(plain, cipherHex, caption) {
            enc.plain = plain
            enc.cipher = cipherHex
            enc.caption = caption
            enc.progress = 0
            replay.restart()
        }
        function onGoto(index) { win.showPage(index) }
    }
    Shortcut { sequence: "Space"; onActivated: spike.encrypt() }
    Shortcut { sequence: "1"; onActivated: win.showPage(0) }
    Shortcut { sequence: "2"; onActivated: win.showPage(1) }
    Component.onCompleted: spike.encrypt()
}
