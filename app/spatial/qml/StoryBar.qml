// The top bar: a depth-3 pill, 12 px from the window edges. One plain sentence about what is
// happening now, then status pills (practice, cloud, engine), the mode, the theme switch and
// Search. At large text sizes the controls wrap under the sentence.
import QtQuick

Surface {
    id: bar
    signal openPalette()
    signal openInsights()
    signal openWorkspaceCloud()
    signal openInspector()

    depth: 3
    padding: 0
    radius: Theme.large ? Theme.rFloat : height / 2
    height: Theme.large ? sentence.implicitHeight + controls.height + 40 : Theme.barH

    Item {
        id: who
        x: Theme.sp5
        width: 20; height: 20
        y: Theme.large ? 16 : (parent.height - height) / 2
        Icon {
            visible: !app.busy
            anchors.centerIn: parent
            size: 18
            name: app.story.role === "security" ? "alert" : app.story.role === "passed" ? "check"
                : app.story.role === "cloud" ? "cloud" : app.story.role === "" ? "lock" : "person"
            color: app.story.role === "security" ? Theme.bad : app.story.role === "passed" ? Theme.ok : Theme.text2
        }
        Canvas {          // working: an arc that turns (a still arc with Reduce motion)
            visible: app.busy
            anchors.fill: parent
            onPaint: { var c = getContext("2d"); c.reset(); c.lineWidth = 2; c.lineCap = "round"; c.strokeStyle = Theme.text
                       c.beginPath(); c.arc(10, 10, 7, 0, Math.PI * 1.4); c.stroke() }
            RotationAnimation on rotation { running: app.busy && !Theme.reduceMotion; loops: Animation.Infinite; from: 0; to: 360; duration: 900 }
        }
    }
    Txt {
        id: sentence
        x: who.x + who.width + Theme.sp3
        y: Theme.large ? 14 : (parent.height - height) / 2
        width: Theme.large ? parent.width - x - Theme.sp5 : controls.x - x - Theme.sp4
        text: app.busy ? T.storyBusy.replace("{label}", app.busyLabel) : app.story.line
        maximumLineCount: Theme.large ? 3 : 1
        elide: Text.ElideRight
        wrapMode: Theme.large ? Text.WordWrap : Text.NoWrap
        lineHeight: Theme.large ? 1.3 : 1.0
        Accessible.role: Accessible.StatusBar
        Accessible.name: text
    }
    Flow {
        id: controls
        readonly property real natural: {
            var w = 0
            for (var i = 0; i < children.length; i++) if (children[i].visible && children[i].width > 0) w += children[i].width + spacing
            return Math.max(0, w - spacing)
        }
        x: Theme.large ? Theme.sp5 : parent.width - width - Theme.sp2
        y: Theme.large ? sentence.y + sentence.height + Theme.sp3 : (parent.height - height) / 2
        width: Theme.large ? parent.width - 2 * Theme.sp5 : natural + 1
        spacing: Theme.sp2
        Item {
            visible: app.practice
            width: children[0].width; height: Math.max(32, Theme.ctlH - 8)
            Pill {
                anchors.verticalCenter: parent.verticalCenter
                visible: app.practice
                text: T.chipPractice; status: "warn"
            }
        }
        Item {
            width: children[0].width; height: Math.max(32, Theme.ctlH - 8)
            Pill {
                anchors.verticalCenter: parent.verticalCenter
                text: app.cloudRunning ? T.chipCloudOn : T.chipCloudOff
                status: app.cloudRunning ? "ok" : "neutral"
                clickable: true
                onClicked: bar.openWorkspaceCloud()
            }
        }
        Item {
            width: children[0].width; height: Math.max(32, Theme.ctlH - 8)
            Pill {
                anchors.verticalCenter: parent.verticalCenter
                text: app.engine === "GPU" ? T.chipGpu : app.engine === "CPU" ? T.chipCpu : T.chipDetecting
                status: app.engine === "GPU" ? "accent" : "neutral"
                clickable: true
                onClicked: bar.openInsights()
            }
        }
        Button {
            kind: "quiet"; small: true
            text: app.mode === "expert" ? T.chipExpert : T.chipBeginner
            onClicked: app.setMode(app.mode === "expert" ? "beginner" : "expert")
        }
        Button {
            visible: Theme.large
            kind: "quiet"; small: true; icon: "inspect"
            text: T.inspectorShort
            onClicked: bar.openInspector()
        }
        Button {
            kind: "ghost"; small: true; minWidth: 40
            icon: Theme.dark ? "sun" : "theme"; text: ""
            Accessible.name: T.themeToggle
            onClicked: app.setTheme(Theme.dark ? "light" : "dark")
        }
        Button {
            kind: "secondary"; small: true; icon: "search"
            text: T.searchShort
            keys: T.searchKeys
            Accessible.name: T.paletteOpen
            onClicked: bar.openPalette()
        }
    }
}
