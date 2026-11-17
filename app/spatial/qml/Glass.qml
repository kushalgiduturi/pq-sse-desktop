// Older name for a region. Quiet glass puts glass only where something floats:
//   floating: a depth-4 Surface (the inspector, the palette); set depth to 3 for raised bars.
//   not floating: a flat region inside the page panel, no fill and no border. Space and
//   hairlines separate content; the panel is the only surface of a page.
import QtQuick

Item {
    id: glass
    default property alias content: inner.data
    property bool floating: false
    property int depth: floating ? 4 : 0
    property real radius: depth === 3 ? Theme.rPanel : Theme.rFloat
    property real padding: floating ? Theme.sp6 : 0
    property bool blur: true
    property real track: 0
    // kept so older call sites still load; they no longer draw anything
    property color rim: Theme.hair
    property real rimWidth: 1
    property real fillOpacity: 1

    Surface {
        visible: glass.depth > 0
        anchors.fill: parent
        depth: Math.max(1, glass.depth)
        radius: glass.radius
        blur: glass.blur
        padding: 0
        track: glass.track
    }
    Item { id: inner; anchors.fill: parent; anchors.margins: glass.padding }
}
