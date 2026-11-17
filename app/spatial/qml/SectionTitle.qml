// A section title row: lg title, optional count and trailing control, a hairline under it.
// Sections are not boxes: space and this hairline separate them.
import QtQuick

Item {
    id: t
    property string text: ""
    property string count: ""
    default property alias trailing: trail.data
    implicitHeight: Math.max(title.implicitHeight, trail.childrenRect.height) + Theme.sp3 + 1
    width: parent ? parent.width : 400
    Row {
        id: title
        spacing: 8
        anchors.verticalCenter: trail.children.length > 0 ? trail.verticalCenter : undefined
        Txt { text: t.text; kind: "lg"; wrapMode: Text.NoWrap }
        Txt { visible: t.count.length > 0; text: t.count; kind: "lg"; tone: "tertiary"; font.weight: Font.Normal; wrapMode: Text.NoWrap }
    }
    Item { id: trail; anchors.right: parent.right; width: childrenRect.width; height: childrenRect.height }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
}
