// Insights: measurements, engine, appearance, advanced settings, data and logs, About.
// In Beginner mode a plain summary comes first and the raw numbers sit behind "More options".
// Quiet glass: flat sections, a metrics strip, charts in accent (CPU) versus text-2 (GPU).
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
            spacing: Theme.sp10
            Txt { text: T.insightsTitle; kind: "xl" }

            // ---------------------------------------------------------- measurements
            TaskCard {
                width: parent.width
                title: T.benchTitle
                summary: app.benchBuild.length === 0 ? T.benchIntro : app.benchSummary
                hasMore: app.benchBuild.length > 0 || app.benchOps.length > 0
                more: page.expert
                id: benchCard
                // the strip: display only, from the measured rows Python returned
                readonly property var largest: app.benchBuild.length === 0 ? null : app.benchBuild.reduce(function (a, b) { return b.occurrences > a.occurrences ? b : a })
                readonly property var fastest: app.benchBuild.length === 0 ? null : app.benchBuild.reduce(function (a, b) { return b.total_s < a.total_s ? b : a })
                readonly property var gpuRow: { for (var i = app.benchBuild.length - 1; i >= 0; i--) if (app.benchBuild[i].gpu) return app.benchBuild[i]; return null }
                Metrics {
                    visible: app.benchBuild.length > 0
                    width: parent.width
                    items: !benchCard.largest || !benchCard.fastest ? [] : [
                        { value: app.engine === "" ? "-" : app.engine, label: T.metricEngine },
                        { value: benchCard.largest.occurrences.toLocaleString(Qt.locale("en_US"), "f", 0), label: T.metricEntries },
                        { value: Theme.fmt(T.metricSeconds, { s: benchCard.fastest.total_s.toFixed(3) }), label: T.metricFastest },
                        { value: benchCard.gpuRow ? Theme.fmt(T.metricTimes, { x: benchCard.gpuRow.total_speedup.toFixed(2) }) : "-", label: T.metricSpeedup }
                    ]
                }
                Item { visible: app.benchBuild.length > 0; width: 1; height: Theme.sp2 }
                Row {
                    visible: app.benchBuild.length > 0
                    width: parent.width
                    spacing: Theme.sp10
                    BarChart { width: (parent.width - Theme.sp10) / 2; rows: app.benchBuild; field: "prf_s"; title: T.benchChartPrf }
                    BarChart { width: (parent.width - Theme.sp10) / 2; rows: app.benchBuild; field: "total_s"; title: T.benchChartTotal }
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
                spacing: Theme.sp10
                readonly property real cardWidth: width > 760 ? (width - Theme.sp10) / 2 : width

                // ------------------------------------------------------ engine
                TaskCard {
                    width: cards.cardWidth
                    title: T.insightsEngine
                    summary: T.insightsEngineNote
                    hasMore: app.gpuReport.length > 0
                    more: app.gpuReport.length > 0
                    Pill { text: app.engine === "GPU" ? T.chipGpu : app.engine === "CPU" ? T.chipCpu : T.chipDetecting; status: app.engine === "GPU" ? "accent" : "neutral" }
                    Lbl { width: parent.width; text: app.engineDetail; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: app.backend; tone: "secondary"; size: Theme.caption }
                    Lbl { width: parent.width; text: app.software ? T.engineDrawSoftware : T.engineDrawGpu; tone: "secondary"; size: Theme.caption }
                    Txt { text: T.engineMode; kind: "sm"; strong: true; topPadding: Theme.sp2 }
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
                    Txt { text: T.settingsTheme; kind: "sm"; strong: true; topPadding: Theme.sp2 }
                    Segmented { width: parent.width; name: T.settingsTheme; labels: [T.themeSystem, T.themeDark, T.themeLight]
                                current: ["system", "dark", "light"].indexOf(app.theme); onChosen: (i) => app.setTheme(["system", "dark", "light"][i]) }
                    Txt { text: T.settingsText; kind: "sm"; strong: true; topPadding: Theme.sp2 }
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: [["small", T.textSmall], ["normal", T.textNormal], ["large", T.textLarge], ["larger", T.textLarger], ["largest", T.textLargest]]
                                      Pick { required property var modelData; text: modelData[1]; selected: app.textSize === modelData[0]; onClicked: app.setTextSize(modelData[0]) } } }
                    Switch { width: parent.width; text: T.settingsMotion; help: T.settingsMotionNote + (app.motionReason.length > 0 ? " " + app.motionReason : "")
                             checked: app.reduceMotionSetting; onToggled: (on) => app.setReduceMotion(on) }
                    Txt { text: T.settingsMode; kind: "sm"; strong: true; topPadding: Theme.sp2 }
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
                        Txt { text: T.advancedKem; kind: "sm"; strong: true; topPadding: Theme.sp2 },
                        Flow { width: parent.width; spacing: 8
                               Repeater { model: app.advanced.kems
                                          Pick { required property string modelData; text: modelData; selected: advanced.kem === modelData; onClicked: advanced.kem = modelData } } },
                        Txt { text: T.advancedSig; kind: "sm"; strong: true; topPadding: Theme.sp2 },
                        Flow { width: parent.width; spacing: 8
                               Repeater { model: app.advanced.sigs
                                          Pick { required property string modelData; text: modelData; selected: advanced.sig === modelData; onClicked: advanced.sig = modelData } } },
                        Txt { text: T.advancedPort; kind: "sm"; strong: true; topPadding: Theme.sp2 },
                        Field { id: portField; width: 160; text: String(app.advanced.port); hint: T.advancedPort },
                        Txt { text: T.advancedTtl; kind: "sm"; strong: true; topPadding: Theme.sp2 },
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
                            spacing: Theme.sp4
                            Txt { width: 200; text: modelData.label; tone: "secondary"; kind: "sm" }
                            Txt { width: column.width - 260; text: modelData.value; kind: "sm"; wrapMode: Text.WrapAnywhere }
                        }
                    }
                    extra: [ Lbl { text: T.aboutLicenses; strong: true },
                             Lbl { width: parent.width; text: app.licenses; size: Theme.caption * 0.95; tone: "secondary"; wrapMode: Text.WrapAnywhere; textFormat: Text.PlainText } ]
                }
            }
        }
    }
}
