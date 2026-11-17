// A task section inside the page panel: a title with a hairline under it, a short state
// sentence, content, one primary action, and "More options" for the rest. Not a box: space
// and the hairline separate sections. "next" adds a Next step status pill to the title;
// "caution" adds a warning icon.
import QtQuick

Item {
    id: card
    property string title: ""
    property string summary: ""
    property bool next: false
    property bool caution: false
    property bool hasMore: false
    property bool more: false
    default property alias body: bodyColumn.data
    property alias extra: extraColumn.data
    // kept so older call sites still load
    property real radius: 0
    property real padding: 0
    property color rim: Theme.hair
    property real rimWidth: 1

    implicitHeight: content.implicitHeight + Theme.sp2
    Accessible.role: Accessible.Grouping
    Accessible.name: title

    Column {
        id: content
        width: parent.width
        spacing: Theme.sp3
        Item {
            width: parent.width
            height: head.implicitHeight + Theme.sp3 + 1
            Row {
                id: head
                width: parent.width
                spacing: Theme.sp2
                Icon { visible: card.caution; name: "alert"; size: 18; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter }
                Txt { id: titleText; text: card.title; kind: "lg"; wrapMode: Text.NoWrap; elide: Text.ElideRight
                      width: Math.min(implicitWidth, parent.width - (card.next ? nextPill.width + 12 : 0) - (card.caution ? 26 : 0)) }
                Pill { id: nextPill; visible: card.next; text: T.nextStep; status: "neutral"; anchors.verticalCenter: parent.verticalCenter }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
        }
        Txt { visible: text.length > 0; width: parent.width; text: card.summary; tone: "secondary" }
        Column { id: bodyColumn; width: parent.width; spacing: Theme.sp3 }
        Button {
            visible: card.hasMore
            kind: "quiet"
            small: true
            icon: card.more ? "chevronDown" : "chevron"
            text: card.more ? T.fewerOptions : T.moreOptions
            onClicked: card.more = !card.more
        }
        Column { id: extraColumn; visible: card.more; width: parent.width; spacing: Theme.sp3 }
    }
}
