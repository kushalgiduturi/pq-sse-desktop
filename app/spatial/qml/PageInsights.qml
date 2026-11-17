// Insights: measurements, engine, appearance, advanced settings, data and logs, About.
// In Beginner mode a plain summary comes first and the raw numbers sit behind "More options".
import QtQuick

Item {
    id: page
    property string exported: ""
    property bool savedAdvanced: false
    readonly property bool expert: app.mode === "expert"

    Flickable {
        anchors.fill: parent
        contentHeight: column.implicitHeight + 16
        clip: true
        Column {
            id: column
            width: parent.width
            spacing: Theme.s16
            Lbl { text: T.insightsTitle; size: Theme.display; strong: true }

            // ---------------------------------------------------------- measurements
            TaskCard {
                width: parent.width
                title: T.benchTitle
                summary: app.benchBuild.length === 0 ? T.benchIntro : app.benchSummary
                hasMore: app.benchBuild.length > 0 || app.benchOps.length > 0
                more: page.expert
                Row {
                    visible: app.benchBuild.length > 0
                    width: parent.width
                    spacing: Theme.s24
                    BarChart { width: (parent.width - Theme.s24) / 2; rows: app.benchBuild; field: "prf_s"; title: T.benchChartPrf }
                    BarChart { width: (parent.width - Theme.s24) / 2; rows: app.benchBuild; field: "total_s"; title: T.benchChartTotal }
                }
                Lbl { visible: app.benchBuild.length > 0; width: parent.width; text: T.insightsEngineNote; tone: "secondary"; size: Theme.caption }
                Flow {
                    width: parent.width; spacing: 10
                    PButton { primary: app.benchBuild.length === 0; enabled: !app.busy; text: T.benchQuick; onClicked: app.runBuildBenchmark(true) }
                    PButton { enabled: !app.busy; text: T.benchFull; onClicked: app.runBuildBenchmark(false) }
                    PButton { enabled: !app.busy; text: T.benchOps; onClicked: app.runOperationBenchmark() }
                    PButton { visible: app.benchBuild.length + app.benchOps.length > 0; text: T.benchExport; onClicked: page.exported = app.exportBenchmarks() }
                }
                Lbl { visible: page.exported.length > 0; width: parent.width; text: T.benchExported.replace("{folder}", page.exported); tone: "secondary"; size: Theme.caption; wrapMode: Text.WrapAnywhere }
                extra: [
                    Lbl { text: T.benchTable; strong: true },
                    Repeater {
                        model: app.benchBuild
                        Lbl { required property var modelData; width: column.width - 60; font.family: Theme.monoFamily; size: Theme.caption; tone: "secondary"
                              text: Theme.fmt(T.benchRow, { n: modelData.occurrences, engine: modelData.engine, prf: modelData.prf_s.toFixed(4), sym: modelData.symmetric_s.toFixed(4), total: modelData.total_s.toFixed(3) })
                                    + (modelData.gpu ? Theme.fmt(T.benchSpeedup, { prf: modelData.prf_speedup.toFixed(1), total: modelData.total_speedup.toFixed(2) }) : "") }
                    },
                    Lbl { visible: app.benchOps.length > 0; text: T.benchOpsNote; tone: "muted"; size: Theme.caption },
                    Repeater {
                        model: app.benchOps
                        Lbl { required property var modelData; width: column.width - 60; font.family: Theme.monoFamily; size: Theme.caption; tone: "secondary"
                              text: Theme.fmt(T.benchOpRow, { op: modelData.operation, params: modelData.params, ms: modelData.ms.toFixed(2) }) }
                    }
                ]
            }

            Flow {
                id: cards
                width: parent.width
                spacing: Theme.s16
                readonly property real cardWidth: width > 880 ? (width - Theme.s16) / 2 : width

                // ------------------------------------------------------ engine
                TaskCard {
                    width: cards.cardWidth
                    title: T.insightsEngine
                    summary: T.insightsEngineNote
                    hasMore: app.gpuReport.length > 0
                    more: app.gpuReport.length > 0
                    Chip { maxWidth: parent.width; text: app.engine === "GPU" ? T.chipGpu : app.engine === "CPU" ? T.chipCpu : T.chipDetecting; mark: "dot"; dot: app.engine === "GPU" ? Theme.accent : Theme.textMuted }
                    Lbl { width: parent.width; text: app.engineDetail; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: app.backend; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: app.software ? T.engineDrawSoftware : T.engineDrawGpu; tone: "secondary"; size: Theme.caption }
                    Lbl { text: T.engineMode; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.engineMode; labels: [T.engineAuto, T.engineCpu, T.engineGpu]
                                current: ["auto", "cpu", "gpu"].indexOf(app.engineMode); onChosen: (i) => app.setEngineMode(["auto", "cpu", "gpu"][i]) }
                    Lbl { width: parent.width; text: T.engineAutoNote; tone: "secondary"; size: Theme.caption }
                    PButton { enabled: !app.busy; text: T.engineSelfTest; Accessible.description: T.engineSelfTestNote; onClicked: app.runGpuSelfTest() }
                    extra: [ Lbl { width: parent.width; text: app.gpuReport; font.family: Theme.monoFamily; size: Theme.caption * 0.95; tone: "secondary"; wrapMode: Text.WrapAnywhere } ]
                }

                // ------------------------------------------------------ appearance
                TaskCard {
                    width: cards.cardWidth
                    title: T.settingsAppearance
                    Lbl { text: T.settingsTheme; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.settingsTheme; labels: [T.themeSystem, T.themeDark, T.themeLight]
                                current: ["system", "dark", "light"].indexOf(app.theme); onChosen: (i) => app.setTheme(["system", "dark", "light"][i]) }
                    Lbl { text: T.settingsText; tone: "muted"; size: Theme.caption }
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: [["small", T.textSmall], ["normal", T.textNormal], ["large", T.textLarge], ["larger", T.textLarger], ["largest", T.textLargest]]
                                      Pick { required property var modelData; text: modelData[1]; selected: app.textSize === modelData[0]; onClicked: app.setTextSize(modelData[0]) } } }
                    Pick { text: T.settingsMotion; selected: app.reduceMotionSetting; onClicked: app.setReduceMotion(!app.reduceMotionSetting) }
                    Lbl { width: parent.width; text: T.settingsMotionNote + (app.motionReason.length > 0 ? " " + app.motionReason : ""); tone: "secondary"; size: Theme.caption }
                    Lbl { text: T.settingsMode; tone: "muted"; size: Theme.caption }
                    Segmented { width: parent.width; name: T.settingsMode; labels: [T.chipBeginner, T.chipExpert]
                                current: page.expert ? 1 : 0; onChosen: (i) => app.setMode(i === 1 ? "expert" : "beginner") }
                    Lbl { width: parent.width; text: page.expert ? T.modeExpert : T.modeBeginner; tone: "secondary"; size: Theme.caption }
                }

                // ------------------------------------------------------ advanced settings
                TaskCard {
                    id: advanced
                    width: cards.cardWidth
                    title: T.advancedTitle
                    summary: T.advancedNote
                    hasMore: true
                    more: page.expert
                    property string kem: app.advanced.kem
                    property string sig: app.advanced.sig
                    extra: [
                        Lbl { text: T.advancedKem; tone: "muted"; size: Theme.caption },
                        Flow { width: parent.width; spacing: 8
                               Repeater { model: app.advanced.kems
                                          Pick { required property string modelData; text: modelData; selected: advanced.kem === modelData; onClicked: advanced.kem = modelData } } },
                        Lbl { text: T.advancedSig; tone: "muted"; size: Theme.caption },
                        Flow { width: parent.width; spacing: 8
                               Repeater { model: app.advanced.sigs
                                          Pick { required property string modelData; text: modelData; selected: advanced.sig === modelData; onClicked: advanced.sig = modelData } } },
                        Lbl { text: T.advancedPort; tone: "muted"; size: Theme.caption },
                        Field { id: portField; width: 160; text: String(app.advanced.port); hint: T.advancedPort },
                        Lbl { text: T.advancedTtl; tone: "muted"; size: Theme.caption },
                        Field { id: ttlField; width: 160; text: String(app.advanced.ttl); hint: T.advancedTtl },
                        PButton { text: page.savedAdvanced ? T.advancedSaved : T.advancedSave
                                  onClicked: { app.setAdvanced(advanced.kem, advanced.sig, parseInt(portField.text) || 0, parseFloat(ttlField.text) || 0); page.savedAdvanced = true } }
                    ]
                }

                // ------------------------------------------------------ data and logs
                TaskCard {
                    width: cards.cardWidth
                    title: T.dataTitle
                    summary: T.logNote
                    hasMore: true
                    Lbl { width: parent.width; text: app.folder("data"); tone: "secondary"; size: Theme.caption; wrapMode: Text.WrapAnywhere }
                    Row { spacing: 10
                          PButton { text: T.dataFolder; onClicked: app.openFolder("data") }
                          PButton { text: T.logFolder; onClicked: app.openFolder("logs") } }
                    onMoreChanged: if (more) app.refreshLog()
                    extra: [ Lbl { width: parent.width; text: app.logTail.length > 0 ? app.logTail : T.logShow; font.family: Theme.monoFamily; size: Theme.caption * 0.95; tone: "secondary"; wrapMode: Text.WrapAnywhere } ]
                }

                // ------------------------------------------------------ about
                TaskCard {
                    width: parent.width
                    title: T.insightsAbout
                    summary: T.appName + ". " + T.aboutResearch
                    hasMore: true
                    Repeater {
                        model: app.aboutRows
                        Row {
                            required property var modelData
                            spacing: 12
                            Lbl { width: 190; text: modelData.label; tone: "muted"; size: Theme.caption }
                            Lbl { width: column.width - 270; text: modelData.value; size: Theme.caption; wrapMode: Text.WrapAnywhere }
                        }
                    }
                    extra: [ Lbl { text: T.aboutLicenses; strong: true },
                             Lbl { width: parent.width; text: app.licenses; size: Theme.caption * 0.95; tone: "secondary"; wrapMode: Text.WrapAnywhere; textFormat: Text.PlainText } ]
                }
            }
        }
    }
}
