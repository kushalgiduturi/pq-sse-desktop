// Button. "primary" is the filled one: at most one per card.
import QtQuick

Item {
    id: btn
    property string text: ""
    property bool primary: false
    property bool danger: false
    property bool quiet: false            // text-only, for "More options"
    property bool busy: false
    signal clicked()

    implicitWidth: Math.max(quiet ? 0 : 120, label.implicitWidth + (quiet ? 16 : 40))
    implicitHeight: quiet ? Theme.controlHeight * 0.8 : Theme.controlHeight
    opacity: enabled ? 1.0 : 0.45
    activeFocusOnTab: true
    scale: press.pressed ? 0.97 : (hover.hovered && enabled ? 1.03 : 1.0)
    Behavior on scale { enabled: !Theme.reduceMotion; SpringAnimation { spring: Theme.hoverSpring; damping: Theme.hoverDamping } }

    Accessible.role: Accessible.Button
    Accessible.name: btn.text
    Accessible.onPressAction: if (btn.enabled) btn.clicked()
    Keys.onReturnPressed: if (enabled) clicked()
    Keys.onEnterPressed: if (enabled) clicked()
    Keys.onSpacePressed: if (enabled) clicked()

    Rectangle {
        anchors.fill: parent
        radius: 14
        color: btn.quiet ? (hover.hovered ? Theme.tint(Theme.glassRaised, 0.9) : "transparent")
             : btn.primary ? (btn.danger ? Theme.fail : Theme.accent) : Theme.tint(Theme.glassRaised, 0.95)
        border.width: btn.activeFocus ? 2 : (btn.primary || btn.quiet ? 0 : 1)
        border.color: btn.activeFocus ? Theme.textPrimary : Theme.tint(Theme.glassStroke, 0.8)
    }
    Text {
        id: label
        anchors.centerIn: parent
        text: btn.text
        color: btn.primary ? Theme.accentOn : (btn.quiet ? Theme.textSecondary : Theme.textPrimary)
        font.family: Theme.fontFamily
        font.pixelSize: btn.quiet ? Theme.body : Theme.bodyLarge * 0.95
        font.weight: Font.DemiBold
    }
    HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
    TapHandler { id: press; enabled: btn.enabled; onTapped: { btn.forceActiveFocus(); btn.clicked() } }
}
