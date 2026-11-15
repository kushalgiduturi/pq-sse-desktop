// Security Lab: placeholder until milestone 5 moves the Attack Lab here.
import QtQuick

Item {
    Column {
        width: parent.width
        spacing: 8
        Lbl { text: T.labTitle; size: Theme.display; strong: true }
        Glass {
            width: Math.min(720, parent.width)
            height: note.implicitHeight + 2 * padding
            Lbl { id: note; width: parent.width; text: T.labSoon; tone: "secondary"; size: Theme.bodyLarge }
        }
    }
}
