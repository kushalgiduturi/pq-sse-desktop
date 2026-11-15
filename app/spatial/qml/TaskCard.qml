// A task card: a title, a short state sentence, content, one primary action, and
// "More options" for the rest. "next" marks the card that holds the next sensible step.
import QtQuick

Glass {
    id: card
    property string title: ""
    property string summary: ""
    property bool next: false
    property bool caution: false
    property bool hasMore: false
    property bool more: false
    default property alias body: bodyColumn.data
    property alias extra: extraColumn.data

    radius: Theme.rCard
    padding: Theme.s24
    rim: next ? Theme.accent : (caution ? Theme.warn : Theme.glassStroke)
    rimWidth: next ? 2 : 1
    implicitHeight: content.implicitHeight + 2 * padding
    Accessible.role: Accessible.Grouping
    Accessible.name: title

    Column {
        id: content
        width: parent.width
        spacing: 10
        Row {
            spacing: 8
            Lbl { visible: card.caution; text: "⚠"; color: Theme.warn; size: Theme.title }
            Lbl { text: card.title; size: Theme.title; strong: true }
        }
        Lbl { visible: text.length > 0; width: parent.width; text: card.summary; tone: "secondary" }
        Column { id: bodyColumn; width: parent.width; spacing: 10 }
        PButton {
            visible: card.hasMore
            quiet: true
            text: (card.more ? T.fewerOptions : T.moreOptions) + (card.more ? "  ▴" : "  ▾")
            onClicked: card.more = !card.more
        }
        Column { id: extraColumn; visible: card.more; width: parent.width; spacing: 10 }
    }
}
