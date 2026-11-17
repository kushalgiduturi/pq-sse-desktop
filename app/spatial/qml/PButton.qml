// Older name for Button: primary (solid accent), danger, quiet (text only), else secondary.
import QtQuick

Button {
    property bool primary: false
    property bool danger: false
    property bool quiet: false
    property bool busy: false
    kind: quiet ? "quiet" : danger ? "danger" : primary ? "primary" : "secondary"
    loading: busy
}
