// Always visible: one plain sentence about what is happening now, and the status chips.
import QtQuick

Glass {
    id: bar
    signal openPalette()
    signal openInsights()
    signal openWorkspaceCloud()
    signal openInspector()

    floating: true
    radius: height / 2
    padding: 0
    height: Theme.large ? sentence.implicitHeight + chips.height + 34 : Math.max(52, sentence.implicitHeight + 24)

    Avatar {
        id: who
        visible: app.story.role !== "" && !app.busy
        who: app.story.role === "security" ? "!" : app.story.role === "passed" ? "✓" : app.story.role
        color: app.story.role === "passed" ? Theme.ok : Theme.roleColor(app.story.role)
        size: 26
        x: 14
        anchors.verticalCenter: parent.verticalCenter
    }
    Rectangle {          // working indicator: a word plus a moving dot (still with Reduce motion)
        visible: app.busy
        x: 14; width: 26; height: 26; radius: 13
        anchors.verticalCenter: parent.verticalCenter
        color: "transparent"; border.width: 3; border.color: Theme.accent
        Rectangle {
            width: 8; height: 8; radius: 4; color: Theme.accent
            x: 9; y: -1
            transformOrigin: Item.Center
        }
        RotationAnimation on rotation { running: app.busy && !Theme.reduceMotion; loops: Animation.Infinite; from: 0; to: 360; duration: 900 }
    }
    Lbl {
        id: sentence
        x: 52
        y: Theme.large ? 12 : (parent.height - height) / 2
        width: Theme.large ? parent.width - 72 : chips.x - 64
        text: app.busy ? T.storyBusy.replace("{label}", app.busyLabel) : app.story.line
        size: Theme.bodyLarge * 0.95
        font.weight: Font.Medium
        maximumLineCount: 2
        elide: Text.ElideRight
        Accessible.role: Accessible.StatusBar
        Accessible.name: text
    }
    Flow {
        id: chips
        anchors.right: parent.right
        anchors.rightMargin: 12
        y: Theme.large ? sentence.y + sentence.height + 8 : (parent.height - height) / 2
        // one line at normal sizes (as wide as the chips need), wrapping under the sentence at large sizes
        readonly property real natural: {
            var w = 0
            for (var i = 0; i < children.length; i++) if (children[i].visible) w += children[i].width + spacing
            return Math.max(0, w - spacing)
        }
        width: Theme.large ? parent.width - 64 : natural + 1
        layoutDirection: Qt.LeftToRight
        spacing: 8
        Chip {
            text: app.practice ? T.chipPractice : T.chipOwn
            mark: "dot"; dot: app.practice ? Theme.warn : Theme.accent
        }
        Chip {
            text: app.cloudRunning ? T.chipCloudOn : T.chipCloudOff
            mark: app.cloudRunning ? "ok" : "dot"; dot: Theme.textMuted
            clickable: true
            onClicked: bar.openWorkspaceCloud()
        }
        Chip {
            text: app.engine === "GPU" ? T.chipGpu : app.engine === "CPU" ? T.chipCpu : T.chipDetecting
            mark: "dot"; dot: app.engine === "GPU" ? Theme.accent : Theme.textMuted
            clickable: true
            onClicked: bar.openInsights()
        }
        Chip {
            text: app.mode === "expert" ? T.chipExpert : T.chipBeginner
            clickable: true
            onClicked: app.setMode(app.mode === "expert" ? "beginner" : "expert")
        }
        Chip { text: T.paletteOpen; clickable: true; onClicked: bar.openPalette() }
        Chip { visible: Theme.large; text: T.inspectorChip; clickable: true; onClicked: bar.openInspector() }
    }
}
