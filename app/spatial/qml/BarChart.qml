// Grouped bars: CPU and GPU, one group per index size, one measure per chart (never two
// axes). Thin bars with rounded tops and a 2 px gap, a legend with marks, a direct value
// label on every bar (there are few), a hover tooltip, and a quiet baseline. Text uses
// text colors; only the bars carry the series color.
import QtQuick

Item {
    id: chart
    property var rows: []                 // [{occurrences, gpu, <field>: seconds}]
    property string field: "total_s"
    property string title: ""
    readonly property var sizes: {
        var seen = []
        for (var i = 0; i < rows.length; i++) if (seen.indexOf(rows[i].occurrences) < 0) seen.push(rows[i].occurrences)
        return seen
    }
    readonly property real peak: {
        var m = 0
        for (var i = 0; i < rows.length; i++) m = Math.max(m, rows[i][field])
        return m > 0 ? m : 1
    }
    readonly property bool hasGpu: rows.some(function (r) { return r.gpu })
    function value(size, gpu) {
        for (var i = 0; i < rows.length; i++) if (rows[i].occurrences === size && rows[i].gpu === gpu) return rows[i][field]
        return -1
    }
    function show(v) { return v >= 10 ? v.toFixed(1) : v >= 1 ? v.toFixed(2) : v.toFixed(3) }

    implicitHeight: 230
    Accessible.role: Accessible.Chart
    Accessible.name: title

    Lbl { id: heading; text: chart.title; strong: true; size: Theme.caption; width: parent.width }
    Row {
        id: legend
        anchors.top: heading.bottom; anchors.topMargin: 6
        spacing: 16
        Repeater {
            model: chart.hasGpu ? [{ name: T.benchLegendCpu, color: Theme.series1 }, { name: T.benchLegendGpu, color: Theme.series2 }]
                                : [{ name: T.benchLegendCpu, color: Theme.series1 }]
            Row {
                required property var modelData
                spacing: 6
                Rectangle { width: 12; height: 12; radius: 3; color: modelData.color; anchors.verticalCenter: parent.verticalCenter }
                Lbl { text: modelData.name; size: Theme.caption; tone: "secondary" }
            }
        }
    }
    Item {
        id: plot
        anchors.top: legend.bottom; anchors.topMargin: 22
        anchors.bottom: parent.bottom; anchors.bottomMargin: 22
        width: parent.width
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.tint(Theme.glassStroke, 0.7) }
        Repeater {
            model: chart.sizes
            Item {
                id: group
                required property var modelData
                required property int index
                x: index * plot.width / chart.sizes.length
                width: plot.width / chart.sizes.length
                height: plot.height
                Repeater {
                    model: chart.hasGpu ? [false, true] : [false]
                    Item {
                        id: bar
                        required property bool modelData
                        required property int index
                        readonly property real v: chart.value(group.modelData, modelData)
                        readonly property real barWidth: Math.min(34, group.width / 4)
                        visible: v >= 0
                        x: group.width / 2 + (chart.hasGpu ? (index === 0 ? -barWidth - 1 : 1) : -barWidth / 2)
                        width: barWidth
                        height: plot.height
                        Rectangle {
                            id: fill
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: Math.max(3, plot.height * bar.v / chart.peak)
                            radius: 4
                            color: bar.modelData ? Theme.series2 : Theme.series1
                            opacity: hover.hovered ? 1 : 0.92
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: Math.min(4, parent.height); color: parent.color }
                            Behavior on height { NumberAnimation { duration: Theme.moveSlow; easing.type: Easing.OutCubic } }
                        }
                        Lbl { anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: fill.top; anchors.bottomMargin: 3
                              text: chart.show(bar.v); size: Theme.caption * 0.92; tone: "secondary"; wrapMode: Text.NoWrap }
                        HoverHandler { id: hover }
                        Rectangle {          // tooltip
                            visible: hover.hovered
                            z: 5
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: fill.top; anchors.bottomMargin: 22
                            width: tip.implicitWidth + 16; height: tip.implicitHeight + 10; radius: 8
                            color: Theme.glassRaised; border.width: 1; border.color: Theme.glassStroke
                            Lbl { id: tip; anchors.centerIn: parent; size: Theme.caption; wrapMode: Text.NoWrap
                                  text: Theme.fmt(T.chartTooltip, { engine: bar.modelData ? T.benchLegendGpu : T.benchLegendCpu, n: group.modelData.toLocaleString(Qt.locale("en_US"), "f", 0), s: bar.v.toFixed(4) }) }
                        }
                    }
                }
                Lbl { anchors.horizontalCenter: parent.horizontalCenter; y: plot.height + 4
                      text: T.benchEntries.replace("{n}", group.modelData.toLocaleString(Qt.locale("en_US"), "f", 0)); size: Theme.caption; tone: "muted"; wrapMode: Text.NoWrap }
            }
        }
    }
}
