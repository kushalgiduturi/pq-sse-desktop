// Depth 0, the world: a quiet ground the glass floats over. A soft vertical shade, one wide
// wash of light, and a calm sample of the Stage scene (three neutral places joined by
// faint paths). No grid, no dots, no color. The blurred copy that glass samples is made by
// the window from this item (one pass, Theme.worldBlur).
import QtQuick
import QtQuick.Effects
import QtQuick.Shapes

Rectangle {
    id: w
    property bool scene: true
    gradient: Gradient {
        GradientStop { position: 0.0; color: Theme.world }
        GradientStop { position: 1.0; color: Theme.worldEdge }
    }
    Rectangle {                   // the wash: one broad, soft light high on the left
        x: w.width * 0.05; y: -w.height * 0.25
        width: w.width * 0.7; height: w.height * 0.8
        radius: width / 2
        color: Theme.worldWash
        layer.enabled: true
        layer.effect: MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 64 }
    }
    Item {
        id: scene
        visible: w.scene
        anchors.fill: parent
        readonly property point a: Qt.point(w.width * 0.16, w.height * 0.62)
        readonly property point c: Qt.point(w.width * 0.5, w.height * 0.30)
        readonly property point b: Qt.point(w.width * 0.84, w.height * 0.62)
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.worldInk; strokeWidth: 1.5; fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                startX: scene.a.x; startY: scene.a.y
                PathQuad { x: scene.c.x; y: scene.c.y; controlX: w.width * 0.28; controlY: w.height * 0.32 }
                PathQuad { x: scene.b.x; y: scene.b.y; controlX: w.width * 0.72; controlY: w.height * 0.32 }
            }
            ShapePath {
                strokeColor: Theme.worldInk; strokeWidth: 1.5; fillColor: "transparent"
                strokeStyle: ShapePath.DashLine; dashPattern: [4, 6]
                startX: scene.a.x; startY: scene.a.y
                PathQuad { x: scene.b.x; y: scene.b.y; controlX: w.width * 0.5; controlY: w.height * 0.82 }
            }
        }
        Repeater {
            model: [scene.a, scene.c, scene.b]
            Rectangle {
                required property point modelData
                x: modelData.x - width / 2; y: modelData.y - height / 2
                width: 120; height: 120; radius: 60
                color: "transparent"
                border.width: 1.5; border.color: Theme.worldInk
            }
        }
    }
}
