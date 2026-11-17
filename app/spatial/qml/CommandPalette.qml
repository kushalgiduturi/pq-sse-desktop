// Command palette (Ctrl+K): type to jump to a destination, a role, a lesson step, a
// setting or a glossary word. Arrow keys, Enter, Esc.
import QtQuick

Item {
    id: palette
    property bool open: false
    property var results: []
    property int cursor: 0
    signal closed()

    anchors.fill: parent
    visible: opacity > 0.01
    opacity: open ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Theme.fast } }

    function show() { open = true; query.text = ""; refresh(); query.focusInput() }
    function hide() { open = false; closed() }
    function refresh() {
        var words = query.text.toLowerCase().split(" ").filter(function (w) { return w.length > 0 })
        var all = app.paletteItems, out = []
        for (var i = 0; i < all.length && out.length < 40; i++) {
            var hay = (all[i].label + " " + all[i].group + " " + all[i].hint).toLowerCase()
            var hit = true
            for (var j = 0; j < words.length; j++) if (hay.indexOf(words[j]) < 0) { hit = false; break }
            if (hit && (words.length > 0 || all[i].group !== "Glossary")) out.push(all[i])
        }
        results = out
        cursor = 0
    }
    function run(index) {
        if (index < 0 || index >= results.length) return
        var id = results[index].id
        hide()
        app.runPalette(id)
    }

    Rectangle { anchors.fill: parent; color: Theme.dim; TapHandler { onTapped: palette.hide() } }

    Glass {
        floating: true
        blur: false
        padding: Theme.sp4
        width: Math.min(680, parent.width - 80)
        height: Math.min(520, parent.height - 160)
        anchors.horizontalCenter: parent.horizontalCenter
        y: 90
        scale: palette.open ? 1 : 0.96
        Behavior on scale { NumberAnimation { duration: Theme.dur3; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeOutCurve } }
        Accessible.role: Accessible.Dialog
        Accessible.name: T.paletteOpen

        Item {
            id: query
            property alias text: field.text
            function focusInput() { field.focusInput() }
            width: parent.width
            height: field.height
            Field {
                id: field
                width: parent.width
                hint: T.paletteHint
                onTextChanged: palette.refresh()
                onAccepted: palette.run(palette.cursor)
                Keys.onDownPressed: palette.cursor = Math.min(palette.results.length - 1, palette.cursor + 1)
                Keys.onUpPressed: palette.cursor = Math.max(0, palette.cursor - 1)
                Keys.onEscapePressed: palette.hide()
            }
        }
        ListView {
            id: list
            anchors.top: query.bottom; anchors.topMargin: 12
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            clip: true
            model: palette.results
            currentIndex: palette.cursor
            spacing: 2
            delegate: Rectangle {
                id: rowItem
                required property var modelData
                required property int index
                width: list.width
                height: Math.max(48, texts.implicitHeight + 14)
                radius: Theme.rSm
                color: index === palette.cursor ? Theme.press : "transparent"
                Accessible.role: Accessible.ListItem
                Accessible.name: modelData.group + ": " + modelData.label
                Column {
                    id: texts
                    x: 14
                    width: parent.width - 150
                    anchors.verticalCenter: parent.verticalCenter
                    Txt { text: rowItem.modelData.label; strong: true; width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap; lineHeight: 1.3 }
                    Txt { visible: text.length > 0; text: rowItem.modelData.hint; tone: "secondary"; kind: "sm"; width: parent.width; maximumLineCount: 2; elide: Text.ElideRight; lineHeight: 1.3 }
                }
                Txt { anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter; text: rowItem.modelData.group; tone: "tertiary"; kind: "sm"; wrapMode: Text.NoWrap }
                HoverHandler { onHoveredChanged: if (hovered) palette.cursor = rowItem.index }
                TapHandler { onTapped: palette.run(rowItem.index) }
            }
            Empty { visible: palette.results.length === 0; anchors.centerIn: parent; icon: "search"; title: T.paletteEmpty }
        }
    }
}
