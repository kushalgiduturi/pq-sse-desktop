// Insights: appearance settings, engine status and About. Benchmarks, logs and the full
// settings arrive in milestone 6.
import QtQuick

Item {
    Flickable {
        anchors.fill: parent
        contentHeight: column.implicitHeight
        clip: true
        Column {
            id: column
            width: parent.width
            spacing: Theme.s16
            Lbl { text: T.insightsTitle; size: Theme.display; strong: true }
            Flow {
                width: parent.width
                spacing: Theme.s16
                readonly property real cardWidth: width > 880 ? (width - Theme.s16) / 2 : width

                TaskCard {
                    width: parent.cardWidth
                    title: T.settingsAppearance
                    Lbl { text: T.settingsTheme; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.settingsTheme; labels: [T.themeSystem, T.themeDark, T.themeLight]
                                current: ["system", "dark", "light"].indexOf(app.theme); onChosen: (i) => app.setTheme(["system", "dark", "light"][i]) }
                    Lbl { text: T.settingsText; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.settingsText; labels: [T.textSmall, T.textNormal, T.textLarge]
                                current: ["small", "normal", "large"].indexOf(app.textSize); onChosen: (i) => app.setTextSize(["small", "normal", "large"][i]) }
                    Pick { text: T.settingsMotion; selected: app.reduceMotionSetting; onClicked: app.setReduceMotion(!app.reduceMotionSetting) }
                    Lbl { width: parent.width; text: T.settingsMotionNote + (app.motionReason.length > 0 ? " " + app.motionReason : ""); tone: "secondary"; size: Theme.caption }
                    Lbl { text: T.settingsMode; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.settingsMode; labels: ["Beginner", "Expert"]
                                current: app.mode === "expert" ? 1 : 0; onChosen: (i) => app.setMode(i === 1 ? "expert" : "beginner") }
                    Lbl { width: parent.width; text: app.mode === "expert" ? T.modeExpert : T.modeBeginner; tone: "secondary"; size: Theme.caption }
                }
                TaskCard {
                    width: parent.cardWidth
                    title: T.insightsEngine
                    summary: T.insightsEngineNote
                    Chip { text: app.engine === "GPU" ? T.chipGpu : app.engine === "CPU" ? T.chipCpu : T.chipDetecting; mark: "dot"; dot: app.engine === "GPU" ? Theme.accent : Theme.textMuted }
                    Lbl { width: parent.width; text: app.engineDetail; tone: "secondary"; size: Theme.caption; visible: app.mode === "expert" || app.engine !== "" }
                    Lbl { width: parent.width; text: app.backend; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: "Drawing: " + (app.software ? "software renderer, effects reduced" : "graphics chip, full effects"); tone: "secondary"; size: Theme.caption }
                }
                TaskCard {
                    width: parent.cardWidth
                    title: T.insightsAbout
                    summary: T.appName + ". " + T.insightsVersion.replace("{v}", app.version)
                    Lbl { width: parent.width; text: "Data folder: " + app.folder("data"); tone: "secondary"; size: Theme.caption; wrapMode: Text.WrapAnywhere }
                    Lbl { width: parent.width; text: "Log folder: " + app.folder("logs"); tone: "secondary"; size: Theme.caption; wrapMode: Text.WrapAnywhere }
                    Lbl { width: parent.width; text: "Research software. Not audited. Do not use it to protect real records."; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: T.insightsSoon; tone: "muted"; size: Theme.caption }
                }
            }
        }
    }
}
