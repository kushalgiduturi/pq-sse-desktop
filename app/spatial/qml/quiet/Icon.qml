// One line icon set: 24 px grid, 1.5 px stroke, round caps and joins, no fills except dots.
import QtQuick

Canvas {
    id: icon
    property string name: "journey"
    property color color: Q.text
    property real size: 20
    width: size; height: size
    renderTarget: Canvas.Image
    onColorChanged: requestPaint()
    onNameChanged: requestPaint()
    onSizeChanged: requestPaint()
    Accessible.ignored: true

    onPaint: {
        var c = getContext("2d")
        c.reset()
        var k = width / 24
        c.scale(k, k)
        c.strokeStyle = icon.color
        c.fillStyle = icon.color
        c.lineWidth = 1.5
        c.lineCap = "round"
        c.lineJoin = "round"
        function line(pts) { c.beginPath(); c.moveTo(pts[0], pts[1]); for (var i = 2; i < pts.length; i += 2) c.lineTo(pts[i], pts[i + 1]); c.stroke() }
        function circle(x, y, r, fill) { c.beginPath(); c.arc(x, y, r, 0, Math.PI * 2); if (fill) c.fill(); else c.stroke() }
        function rrect(x, y, w, h, r) {
            c.beginPath(); c.moveTo(x + r, y); c.lineTo(x + w - r, y); c.arcTo(x + w, y, x + w, y + r, r); c.lineTo(x + w, y + h - r)
            c.arcTo(x + w, y + h, x + w - r, y + h, r); c.lineTo(x + r, y + h); c.arcTo(x, y + h, x, y + h - r, r); c.lineTo(x, y + r)
            c.arcTo(x, y, x + r, y, r); c.closePath(); c.stroke()
        }
        switch (name) {
        case "journey":   // a path ending in a flag
            c.beginPath(); c.moveTo(5, 20); c.bezierCurveTo(5, 13, 15, 16, 15, 9); c.stroke()
            line([15, 9, 15, 3.5]); line([15, 4, 20, 5.8, 15, 7.6]); circle(5, 20, 1.2, true); break
        case "stage":     // two people and a cloud between them
            circle(5, 9, 2.2); line([2, 17, 2.4, 14.4, 5, 13, 7.6, 14.4, 8, 17])
            circle(19, 9, 2.2); line([16, 17, 16.4, 14.4, 19, 13, 21.6, 14.4, 22, 17])
            c.beginPath(); c.moveTo(9.5, 7.5); c.arc(11, 6.5, 1.8, Math.PI * 0.8, Math.PI * 1.9); c.arc(13.4, 6.3, 1.6, Math.PI * 1.2, Math.PI * 0.2); c.lineTo(9.5, 7.8); c.stroke(); break
        case "workspace": // a desk with tools
            rrect(3, 5, 18, 12, 2.5); line([8, 21, 16, 21]); line([12, 17, 12, 21]); line([7, 10, 12, 10]); line([7, 13, 15, 13]); break
        case "lab":       // a shield with a check
            c.beginPath(); c.moveTo(12, 3); c.lineTo(19, 6); c.lineTo(19, 11.5); c.bezierCurveTo(19, 16, 15.8, 19.3, 12, 21)
            c.bezierCurveTo(8.2, 19.3, 5, 16, 5, 11.5); c.lineTo(5, 6); c.closePath(); c.stroke(); line([9, 12, 11.2, 14.2, 15.2, 9.8]); break
        case "insights":  // three bars on a baseline
            line([4, 20, 20, 20]); line([7, 17, 7, 12]); line([12, 17, 12, 6]); line([17, 17, 17, 9]); break
        case "search":
            circle(10.5, 10.5, 6); line([15, 15, 20, 20]); break
        case "theme":     // half moon
            c.beginPath(); c.arc(12, 12, 8, Math.PI * 0.5, Math.PI * 1.5); c.bezierCurveTo(16, 6, 16, 18, 12, 20); c.stroke(); break
        case "sun":
            circle(12, 12, 4); line([12, 2.5, 12, 4.5]); line([12, 19.5, 12, 21.5]); line([2.5, 12, 4.5, 12]); line([19.5, 12, 21.5, 12])
            line([5.3, 5.3, 6.7, 6.7]); line([17.3, 17.3, 18.7, 18.7]); line([5.3, 18.7, 6.7, 17.3]); line([17.3, 6.7, 18.7, 5.3]); break
        case "inspect":   // stacked layers
            line([12, 4, 20, 8.5, 12, 13, 4, 8.5, 12, 4]); line([4, 12.5, 12, 17, 20, 12.5]); line([4, 16.5, 12, 21, 20, 16.5]); break
        case "lock":
            rrect(5, 10.5, 14, 10, 2.5); c.beginPath(); c.moveTo(8, 10.5); c.lineTo(8, 7.5); c.arc(12, 7.5, 4, Math.PI, 0); c.lineTo(16, 10.5); c.stroke()
            line([12, 14.5, 12, 16.5]); break
        case "key":
            circle(7.5, 12, 3.5); line([11, 12, 20.5, 12, 20.5, 15]); line([17, 12, 17, 14.5]); break
        case "document":
            c.beginPath(); c.moveTo(6, 3); c.lineTo(14, 3); c.lineTo(19, 8); c.lineTo(19, 21); c.lineTo(6, 21); c.closePath(); c.stroke()
            line([14, 3, 14, 8, 19, 8]); line([9, 13, 16, 13]); line([9, 16.5, 14, 16.5]); break
        case "person":
            circle(12, 8, 3.5); line([5, 20.5, 5.6, 16.5, 9, 14, 15, 14, 18.4, 16.5, 19, 20.5]); break
        case "cloud":
            c.beginPath(); c.moveTo(7, 18); c.arc(7, 14, 4, Math.PI * 0.5, Math.PI * 1.5); c.arc(12, 9.5, 5, Math.PI * 1.15, Math.PI * 1.95)
            c.arc(17, 13.5, 4.5, Math.PI * 1.45, Math.PI * 0.5); c.closePath(); c.stroke(); break
        case "check":
            line([5, 12.5, 10, 17.5, 19, 7.5]); break
        case "cross":
            line([6, 6, 18, 18]); line([18, 6, 6, 18]); break
        case "alert":     // triangle with a mark
            c.beginPath(); c.moveTo(12, 3.5); c.lineTo(21, 19.5); c.lineTo(3, 19.5); c.closePath(); c.stroke(); line([12, 9.5, 12, 13.5]); circle(12, 16.5, 0.9, true); break
        case "chevron":
            line([9, 6, 15, 12, 9, 18]); break
        case "chevronDown":
            line([6, 9, 12, 15, 18, 9]); break
        case "plus":
            line([12, 5, 12, 19]); line([5, 12, 19, 12]); break
        case "close":
            line([6.5, 6.5, 17.5, 17.5]); line([17.5, 6.5, 6.5, 17.5]); break
        case "play":
            c.beginPath(); c.moveTo(8, 5); c.lineTo(19, 12); c.lineTo(8, 19); c.closePath(); c.stroke(); break
        case "pause":
            line([8.5, 5.5, 8.5, 18.5]); line([15.5, 5.5, 15.5, 18.5]); break
        case "empty":     // an open tray
            line([3, 13, 7, 6, 17, 6, 21, 13]); c.beginPath(); c.moveTo(3, 13); c.lineTo(3, 19); c.lineTo(21, 19); c.lineTo(21, 13); c.lineTo(15.5, 13)
            c.lineTo(14.5, 15.5); c.lineTo(9.5, 15.5); c.lineTo(8.5, 13); c.closePath(); c.stroke(); break
        case "copy":
            rrect(8, 8, 12, 12, 2.5); c.beginPath(); c.moveTo(16, 8); c.lineTo(16, 6); c.arcTo(16, 4, 14, 4, 2); c.lineTo(6, 4); c.arcTo(4, 4, 4, 6, 2)
            c.lineTo(4, 14); c.arcTo(4, 16, 6, 16, 2); c.lineTo(8, 16); c.stroke(); break
        default:
            circle(12, 12, 7)
        }
    }
}
