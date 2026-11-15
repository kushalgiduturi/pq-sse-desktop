// Small line icons drawn in code (no icon font, no image files).
import QtQuick

Canvas {
    id: icon
    property string name: "journey"
    property color color: Theme.textPrimary
    width: 24; height: 24
    onColorChanged: requestPaint()
    onNameChanged: requestPaint()
    onPaint: {
        var c = getContext("2d")
        c.reset()
        c.strokeStyle = icon.color
        c.fillStyle = icon.color
        c.lineWidth = 2
        c.lineCap = "round"
        c.lineJoin = "round"
        var w = width, h = height
        if (name === "journey") {                 // a path with a flag at the end
            c.beginPath(); c.moveTo(w * 0.15, h * 0.85); c.bezierCurveTo(w * 0.15, h * 0.4, w * 0.6, h * 0.8, w * 0.6, h * 0.35); c.stroke()
            c.beginPath(); c.moveTo(w * 0.6, h * 0.4); c.lineTo(w * 0.6, h * 0.1); c.lineTo(w * 0.9, h * 0.22); c.lineTo(w * 0.6, h * 0.33); c.fill()
        } else if (name === "stage") {            // three parties
            c.beginPath(); c.arc(w * 0.2, h * 0.6, w * 0.13, 0, 6.3); c.fill()
            c.beginPath(); c.arc(w * 0.8, h * 0.6, w * 0.13, 0, 6.3); c.fill()
            c.strokeRect(w * 0.38, h * 0.18, w * 0.24, h * 0.24)
            c.beginPath(); c.moveTo(w * 0.33, h * 0.6); c.lineTo(w * 0.67, h * 0.6); c.stroke()
        } else if (name === "workspace") {        // cards
            c.strokeRect(w * 0.14, h * 0.14, w * 0.3, h * 0.3); c.strokeRect(w * 0.56, h * 0.14, w * 0.3, h * 0.3)
            c.strokeRect(w * 0.14, h * 0.56, w * 0.3, h * 0.3); c.strokeRect(w * 0.56, h * 0.56, w * 0.3, h * 0.3)
        } else if (name === "lab") {              // shield
            c.beginPath(); c.moveTo(w * 0.5, h * 0.1); c.lineTo(w * 0.85, h * 0.25); c.lineTo(w * 0.85, h * 0.5)
            c.bezierCurveTo(w * 0.85, h * 0.75, w * 0.65, h * 0.85, w * 0.5, h * 0.92)
            c.bezierCurveTo(w * 0.35, h * 0.85, w * 0.15, h * 0.75, w * 0.15, h * 0.5); c.lineTo(w * 0.15, h * 0.25); c.closePath(); c.stroke()
            c.beginPath(); c.moveTo(w * 0.36, h * 0.5); c.lineTo(w * 0.47, h * 0.62); c.lineTo(w * 0.66, h * 0.38); c.stroke()
        } else if (name === "insights") {         // bars
            c.fillRect(w * 0.16, h * 0.55, w * 0.16, h * 0.3); c.fillRect(w * 0.42, h * 0.32, w * 0.16, h * 0.53); c.fillRect(w * 0.68, h * 0.14, w * 0.16, h * 0.71)
        } else if (name === "search") {
            c.beginPath(); c.arc(w * 0.43, h * 0.43, w * 0.26, 0, 6.3); c.stroke()
            c.beginPath(); c.moveTo(w * 0.63, h * 0.63); c.lineTo(w * 0.88, h * 0.88); c.stroke()
        } else if (name === "lock") {
            c.fillRect(w * 0.2, h * 0.45, w * 0.6, h * 0.45)
            c.beginPath(); c.arc(w * 0.5, h * 0.42, w * 0.2, 3.14, 0); c.stroke()
        } else if (name === "close") {
            c.beginPath(); c.moveTo(w * 0.25, h * 0.25); c.lineTo(w * 0.75, h * 0.75); c.moveTo(w * 0.75, h * 0.25); c.lineTo(w * 0.25, h * 0.75); c.stroke()
        } else if (name === "inspect") {          // layers
            c.beginPath(); c.moveTo(w * 0.5, h * 0.12); c.lineTo(w * 0.9, h * 0.35); c.lineTo(w * 0.5, h * 0.58); c.lineTo(w * 0.1, h * 0.35); c.closePath(); c.stroke()
            c.beginPath(); c.moveTo(w * 0.1, h * 0.55); c.lineTo(w * 0.5, h * 0.78); c.lineTo(w * 0.9, h * 0.55); c.stroke()
        }
    }
}
