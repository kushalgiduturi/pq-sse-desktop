// Workspace: the working tools, by role. A rail on the left picks the role; each role
// shows only its own task cards, with one filled button on the card that is next.
import QtQuick
import QtQuick.Dialogs

Item {
    id: page
    signal inspect(int index)

    readonly property var owner: app.state.owner
    readonly property var cloud: app.state.cloud
    readonly property var doctors: app.state.receivers
    readonly property string role: app.role
    readonly property bool isAlice: role === "alice"
    readonly property bool isCloud: role === "cloud"
    readonly property var doctor: {
        for (var i = 0; i < doctors.length; i++) if (doctors[i].name === role) return doctors[i]
        return { name: role, display: cap(role), open: false, paired: false, joined: false, groups: [], result: {}, opened: {}, fresh: true }
    }
    property string group: ""
    property string revokeUid: ""
    property string policy: "R"
    property var approve: ({})              // uid -> list of group names ticked
    readonly property string activeGroup: {
        var names = owner.groups.map(function (g) { return g.name })
        return names.indexOf(group) >= 0 ? group : (names.length > 0 ? names[0] : "")
    }
    readonly property var groupState: {
        for (var i = 0; i < owner.groups.length; i++) if (owner.groups[i].name === activeGroup) return owner.groups[i]
        return { name: "", docs: [], dirty: false, version: 0, epoch: 0, freshHours: 0 }
    }
    readonly property string aliceNext: !owner.open || !owner.paired ? "keys" : owner.groups.length === 0 || owner.pending.length > 0 ? "people"
                                      : owner.groups.some(function (g) { return g.dirty }) ? "publish" : "documents"
    readonly property string doctorNext: !doctor.open ? "keys" : !doctor.joined ? "join" : "search"
    function cap(s) { return s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s }
    function fill(text, map) { for (var k in map) text = text.split("{" + k + "}").join(map[k]); return text }
    function ticked(uid, g) { return (approve[uid] || []).indexOf(g) >= 0 }
    function tick(uid, g) {
        var copy = {}; for (var k in approve) copy[k] = approve[k].slice()
        var list = copy[uid] || []
        var at = list.indexOf(g)
        if (at >= 0) list.splice(at, 1); else list.push(g)
        copy[uid] = list
        approve = copy
    }

    // ---------------------------------------------------------------- role rail
    Glass {
        id: rail
        width: 220 * Math.max(1, Theme.scale)
        height: parent.height
        padding: Theme.s12
        Column {
            width: parent.width
            spacing: 6
            Lbl { text: T.workAs; tone: "muted"; size: Theme.caption; leftPadding: 8 }
            Repeater {
                model: ["alice"].concat(page.doctors.map(function (d) { return d.name }),
                                        page.isAlice || page.isCloud || page.doctors.some(function (d) { return d.name === page.role }) ? [] : [page.role], ["cloud"])
                Rectangle {
                    id: roleItem
                    required property string modelData
                    readonly property bool on: page.role === modelData
                    width: rail.width - 2 * rail.padding
                    height: 60 * Math.max(1, Theme.scale)
                    radius: 16
                    color: on ? Theme.tint(Theme.glassRaised, 1) : "transparent"
                    border.width: on || activeFocus ? 2 : 0
                    border.color: activeFocus ? Theme.textPrimary : Theme.accent
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: page.cap(modelData)
                    Accessible.checked: on
                    Keys.onReturnPressed: app.setRole(modelData)
                    Keys.onSpacePressed: app.setRole(modelData)
                    Avatar { who: page.cap(roleItem.modelData); size: 38; x: 10; anchors.verticalCenter: parent.verticalCenter; color: Theme.roleColor(roleItem.modelData) }
                    Column {
                        x: 58; anchors.verticalCenter: parent.verticalCenter
                        Lbl { text: page.cap(roleItem.modelData); strong: true; size: Theme.bodyLarge * 0.95 }
                        Lbl { text: roleItem.modelData === "alice" ? "Data owner" : roleItem.modelData === "cloud" ? "Storage server" : "Doctor"; tone: "secondary"; size: Theme.caption }
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.setRole(roleItem.modelData) }
                }
            }
            Item { width: 1; height: 8 }
            Field { id: newPerson; width: parent.width; hint: T.addPersonHint; onAccepted: addButton.clicked() }
            PButton { id: addButton; width: parent.width; text: T.addPerson; enabled: newPerson.text.trim().length > 0
                      onClicked: { app.setRole(newPerson.text.trim().toLowerCase()); newPerson.clear() } }
        }
    }

    // ---------------------------------------------------------------- cards
    Flickable {
        id: scroller
        anchors.left: rail.right; anchors.leftMargin: Theme.s24
        anchors.right: parent.right
        height: parent.height
        contentHeight: content.implicitHeight + 24
        clip: true
        readonly property real cardWidth: width > 880 ? (width - Theme.s16) / 2 : width

        Column {
            id: content
            width: parent.width
            spacing: Theme.s16
            Column {
                width: parent.width
                Lbl { text: page.fill(T.workspaceTitle, { role: page.cap(page.role) }); size: Theme.headline; strong: true }
                Lbl { text: T.workspaceSub + (app.practice ? " " + T.practicePass : ""); tone: "secondary"; width: parent.width }
            }

            // ============================================================ Alice
            Flow {
                visible: page.isAlice
                width: parent.width
                spacing: Theme.s16

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardKeys
                    next: page.aliceNext === "keys"
                    summary: !page.owner.exists ? T.aliceKeysNew : !page.owner.open ? T.aliceKeysLocked
                           : page.fill(T.aliceKeysOpen, { fp: page.owner.fingerprint }) + " " + (page.owner.paired ? T.alicePaired : T.aliceNotPaired)
                    Field { id: ownerPass; visible: !page.owner.open; width: parent.width; secret: true; hint: T.passphrase; onAccepted: ownerOpen.clicked() }
                    Lbl { visible: !page.owner.open; width: parent.width; text: T.passphraseHint; tone: "muted"; size: Theme.caption }
                    PButton { id: ownerOpen; visible: !page.owner.open; primary: page.aliceNext === "keys"; enabled: !app.busy
                              text: page.owner.exists ? T.aliceKeysBtnOpen : T.aliceKeysBtnNew
                              onClicked: { app.openOwner(ownerPass.text); ownerPass.clear() } }
                    PButton { visible: page.owner.open && !page.owner.paired; primary: true; enabled: !app.busy && page.cloud.running
                              text: T.alicePairBtn; onClicked: app.pairOwnerAndCloud() }
                    Lbl { visible: page.owner.open && !page.owner.paired && !page.cloud.running; width: parent.width; tone: "muted"; size: Theme.caption
                          text: "Start the cloud first: choose Cloud in the rail on the left." }
                }

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardDocuments
                    next: page.aliceNext === "documents"
                    hasMore: page.owner.groups.length > 0
                    summary: page.owner.groups.length === 0 ? T.docsNoGroup
                           : page.groupState.docs.length === 0 ? T.docsNone : page.fill(T.docsCount, { n: page.groupState.docs.length, g: page.activeGroup })
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: page.owner.groups
                                      Pick { required property var modelData; text: modelData.name; selected: page.activeGroup === modelData.name; onClicked: page.group = modelData.name } } }
                    Repeater {
                        model: page.groupState.docs
                        Rectangle {
                            id: docRow
                            required property var modelData
                            width: parent.width; height: Math.max(40, docTitle.implicitHeight + 14); radius: 10
                            color: Theme.tint(Theme.glassRaised, 0.8); border.width: 1; border.color: Theme.tint(Theme.glassStroke, 0.5)
                            Lbl { id: docTitle; x: 12; width: parent.width - 110; anchors.verticalCenter: parent.verticalCenter; text: docRow.modelData.title; maximumLineCount: 1; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                            PButton { anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter; quiet: true; text: T.docsDelete
                                      enabled: !app.busy; Accessible.name: T.docsDelete + " " + docRow.modelData.title
                                      onClicked: app.deleteDocument(page.activeGroup, docRow.modelData.id) }
                        }
                    }
                    Field { id: docTitleField; visible: page.owner.groups.length > 0; width: parent.width; hint: T.docsTitleHint }
                    Rectangle {
                        visible: page.owner.groups.length > 0
                        width: parent.width; height: 96; radius: 12
                        color: Theme.tint(Theme.roomTop, 0.55); border.width: docText.activeFocus ? 2 : 1
                        border.color: docText.activeFocus ? Theme.accent : Theme.tint(Theme.glassStroke, 0.8)
                        Lbl { visible: docText.text.length === 0; x: 14; y: 10; text: T.docsTextHint; tone: "muted" }
                        Flickable {
                            anchors.fill: parent; anchors.margins: 10; clip: true; contentHeight: docText.implicitHeight
                            TextEdit { id: docText; width: parent.width; wrapMode: TextEdit.Wrap; color: Theme.textPrimary; selectionColor: Theme.accent
                                       font.family: Theme.fontFamily; font.pixelSize: Theme.body; activeFocusOnTab: true; selectByMouse: true
                                       Accessible.role: Accessible.EditableText; Accessible.name: T.docsTextHint; KeyNavigation.priority: KeyNavigation.BeforeItem; KeyNavigation.tab: docAdd }
                        }
                    }
                    PButton { id: docAdd; visible: page.owner.groups.length > 0; primary: page.aliceNext === "documents"; enabled: !app.busy && docText.text.trim().length > 0
                              text: T.docsAddBtn
                              onClicked: { app.addDocument(page.activeGroup, docTitleField.text, docText.text); docTitleField.clear(); docText.text = "" } }
                    extra: [ PButton { text: T.docsImport; enabled: !app.busy; onClicked: fileDialog.open() } ]
                }

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardPeople
                    next: page.aliceNext === "people"
                    hasMore: page.owner.open
                    more: page.owner.open && page.owner.groups.length === 0
                    summary: !page.owner.open ? "" : (page.owner.people.length === 0 ? T.peopleNone : "")
                             + (page.owner.pending.length > 0 ? " " + page.fill(T.peopleWaiting, { n: page.owner.pending.length }) : "")
                    Repeater {
                        model: page.owner.people
                        Chip { required property var modelData
                               text: page.cap(modelData.name) + ": " + (modelData.revoked ? T.peopleRevoked : modelData.groups.join(", "))
                               mark: modelData.revoked ? "fail" : "ok" }
                    }
                    Repeater {
                        model: page.owner.pending
                        Column {
                            id: pend
                            required property var modelData
                            width: parent.width; spacing: 6
                            Lbl { width: parent.width; text: page.cap(pend.modelData.name) + " asks to join. Key fingerprint: " + pend.modelData.fingerprint; strong: true }
                            Flow { width: parent.width; spacing: 8
                                   Repeater { model: page.owner.groups
                                              Pick { required property var modelData; text: modelData.name; selected: page.ticked(pend.modelData.uid, modelData.name)
                                                     onClicked: page.tick(pend.modelData.uid, modelData.name) } } }
                            PButton { primary: true; enabled: !app.busy && (page.approve[pend.modelData.uid] || []).length > 0; text: T.peopleApprove
                                      onClicked: app.approveJoin(pend.modelData.uid, page.approve[pend.modelData.uid]) }
                        }
                    }
                    extra: [
                        Field { id: groupName; width: parent.width; hint: T.peopleNewGroup; onAccepted: groupCreate.clicked() },
                        Row { spacing: 10
                              PButton { id: groupCreate; primary: page.owner.groups.length === 0; enabled: !app.busy && groupName.text.trim().length > 0; text: T.peopleCreateGroup
                                        onClicked: { app.createGroup(groupName.text); groupName.clear() } }
                              PButton { text: T.peopleRefresh; enabled: !app.busy; onClicked: app.refresh() } }
                    ]
                }

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardPublish
                    next: page.aliceNext === "publish"
                    summary: page.owner.groups.length === 0 ? "" : T.publishWhy
                    Repeater {
                        model: page.owner.groups
                        Column {
                            id: pub
                            required property var modelData
                            width: parent.width; spacing: 6
                            Lbl { width: parent.width
                                  text: page.fill(T.publishState, { g: pub.modelData.name, ver: pub.modelData.version, e: pub.modelData.epoch,
                                                                    fresh: pub.modelData.dirty ? T.publishDirty : T.publishClean + " Valid for " + pub.modelData.freshHours + " more hours." })
                                  tone: pub.modelData.dirty ? "primary" : "secondary" }
                            PButton { primary: pub.modelData.dirty; enabled: !app.busy; text: T.publishBtn + ": " + pub.modelData.name; onClicked: app.publish(pub.modelData.name) }
                        }
                    }
                }

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardRevoke
                    caution: true
                    summary: page.owner.people.filter(function (p) { return !p.revoked }).length === 0 ? T.revokeNobody : T.revokeWhy
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: page.owner.people.filter(function (p) { return !p.revoked })
                                      Pick { required property var modelData; text: page.cap(modelData.name); selected: page.revokeUid === modelData.uid; onClicked: page.revokeUid = modelData.uid } } }
                    Segmented { visible: page.owner.people.length > 0; width: parent.width; name: "Policy"; labels: [T.revokeQuick, T.revokeThorough]
                                current: page.policy === "R" ? 0 : 1; onChosen: (i) => page.policy = i === 0 ? "R" : "RE" }
                    Lbl { visible: page.owner.people.length > 0; width: parent.width; text: page.policy === "R" ? T.revokeQuickNote : T.revokeThoroughNote; tone: "secondary" }
                    PButton { visible: page.owner.people.length > 0; danger: true; primary: page.revokeUid !== ""; enabled: !app.busy && page.revokeUid !== ""; text: T.revokeBtn
                              onClicked: { app.revoke(page.revokeUid, page.policy); page.revokeUid = "" } }
                }
            }

            // ============================================================ a doctor
            Flow {
                visible: !page.isAlice && !page.isCloud
                width: parent.width
                spacing: Theme.s16

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardKeys
                    next: page.doctorNext === "keys"
                    summary: page.fill(page.doctor.fresh ? T.doctorKeysNew : page.doctor.open ? T.doctorKeysOpen : T.doctorKeysLocked, { who: page.doctor.display })
                    Field { id: doctorPass; visible: !page.doctor.open; width: parent.width; secret: true; hint: T.passphrase; onAccepted: doctorOpen.clicked() }
                    PButton { id: doctorOpen; visible: !page.doctor.open; primary: true; enabled: !app.busy
                              text: page.fill(page.doctor.fresh ? T.doctorKeysBtnNew : T.doctorKeysBtnOpen, { who: page.doctor.display })
                              onClicked: { app.openReceiver(page.role, doctorPass.text); doctorPass.clear() } }
                }
                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardJoin
                    next: page.doctorNext === "join"
                    summary: !page.doctor.open ? "" : page.doctor.joined ? page.fill(T.joinDone, { who: page.doctor.display, groups: page.doctor.groups.join(", ") })
                           : !page.doctor.paired ? page.fill(T.joinNotPaired, { who: page.doctor.display }) : page.fill(T.joinAsk, { who: page.doctor.display }) + " " + T.joinWaiting
                    PButton { visible: page.doctor.open && !page.doctor.paired; primary: true; enabled: !app.busy; text: T.joinPairBtn; onClicked: app.pairReceiver(page.role) }
                    Row { visible: page.doctor.open && page.doctor.paired; spacing: 10
                          PButton { visible: !page.doctor.joined; primary: true; enabled: !app.busy; text: T.joinAskBtn; onClicked: app.sendJoin(page.role) }
                          PButton { enabled: !app.busy; text: T.joinFetchBtn; onClicked: app.fetchMail(page.role) } }
                }
                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardSearch
                    next: page.doctorNext === "search"
                    summary: !page.doctor.joined ? T.searchNone
                           : page.doctor.result.keyword ? page.fill(T.searchResults, { n: page.doctor.result.hits.length, w: page.doctor.result.keyword, g: page.doctor.result.group }) : ""
                    property string searchGroup: ""
                    readonly property string useGroup: page.doctor.groups.indexOf(searchGroup) >= 0 ? searchGroup : (page.doctor.groups.length > 0 ? page.doctor.groups[0] : "")
                    id: searchCard
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: page.doctor.groups
                                      Pick { required property string modelData; text: modelData; selected: searchCard.useGroup === modelData; onClicked: searchCard.searchGroup = modelData } } }
                    Field { id: keyword; visible: page.doctor.joined; width: parent.width; hint: T.searchHint; onAccepted: searchButton.clicked() }
                    PButton { id: searchButton; visible: page.doctor.joined; primary: true; enabled: !app.busy && keyword.text.trim().length > 0; text: T.searchBtn
                              onClicked: app.search(page.role, searchCard.useGroup, keyword.text) }
                }
                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardVerify
                    readonly property var checks: page.doctor.result.checks || []
                    id: verifyCard
                    rim: page.doctor.result.failed ? Theme.fail : Theme.glassStroke
                    summary: checks.length === 0 ? T.verifyNone : page.doctor.result.failed ? T.verifyFailed : page.fill(T.verifyAll, { n: checks.length })
                    Repeater {
                        model: verifyCard.checks
                        Chip { required property var modelData; text: modelData.name + (modelData.ok ? "" : ": " + modelData.detail); mark: modelData.ok ? "ok" : "fail" }
                    }
                    PButton { visible: verifyCard.checks.length > 0 && events.count > 0; text: T.inspectorOpen; onClicked: page.inspect(events.count - 1) }
                }
                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardOpen
                    summary: !page.doctor.result.hits || page.doctor.result.hits.length === 0 ? T.openNone : ""
                    Flow { width: parent.width; spacing: 8
                           Repeater { model: page.doctor.result.hits || []
                                      PButton { required property var modelData; text: page.fill(T.openBtn, { id: modelData.id }); enabled: !app.busy
                                                onClicked: app.openDocument(page.role, page.doctor.result.group, modelData.id, modelData.epoch) } } }
                    Lbl { visible: page.doctor.opened.title !== undefined; width: parent.width; text: page.doctor.opened.title || ""; strong: true; size: Theme.bodyLarge }
                    Lbl { visible: page.doctor.opened.title !== undefined; width: parent.width; text: page.doctor.opened.text || ""; tone: "secondary" }
                }
            }

            // ============================================================ the cloud
            Flow {
                visible: page.isCloud
                width: parent.width
                spacing: Theme.s16

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardServer
                    next: !page.cloud.running
                    hasMore: page.cloud.running
                    summary: page.cloud.running ? T.serverOn + " Port " + page.cloud.port + "." : T.serverOff
                    Field { id: cloudPass; visible: !page.cloud.running; width: parent.width; secret: true; hint: T.passphrase; onAccepted: cloudStart.clicked() }
                    PButton { id: cloudStart; visible: !page.cloud.running; primary: true; enabled: !app.busy; text: T.serverStart
                              onClicked: { app.startCloud(cloudPass.text); cloudPass.clear() } }
                    Lbl { visible: page.cloud.running; width: parent.width; text: page.cloud.line; tone: "muted"; size: Theme.caption; font.family: Theme.monoFamily; wrapMode: Text.WrapAnywhere }
                    extra: [ PButton { text: T.serverStop; enabled: !app.busy; onClicked: app.stopCloud() } ]
                }
                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardStores
                    summary: page.cloud.docs + page.cloud.entries === 0 ? T.storesNone : page.fill(T.storesNote, { docs: page.cloud.docs, entries: page.cloud.entries })
                    Repeater {
                        model: page.cloud.storedDocs
                        Lbl { required property var modelData; width: parent.width; text: modelData.hex.replace(/(..)/g, "$1 ") + " ... (" + modelData.bytes + " bytes)"
                              font.family: Theme.monoFamily; size: Theme.caption; tone: "muted"; wrapMode: Text.WrapAnywhere; maximumLineCount: 2; elide: Text.ElideRight }
                    }
                    Repeater {
                        model: page.cloud.storedEntries
                        Lbl { required property var modelData; width: parent.width; text: "address " + modelData.address + "...  value " + modelData.value
                              font.family: Theme.monoFamily; size: Theme.caption; tone: "muted"; wrapMode: Text.WrapAnywhere }
                    }
                }
                TaskCard {
                    width: scroller.width
                    title: T.cardLog
                    summary: page.cloud.log.length === 0 ? T.logNone : T.logNote
                    Repeater {
                        model: page.cloud.log.slice(0, 14)
                        Row {
                            required property var modelData
                            spacing: 16
                            Lbl { width: 70; text: modelData.time; tone: "muted"; font.family: Theme.monoFamily; size: Theme.caption }
                            Lbl { width: 150; text: modelData.endpoint; size: Theme.caption; strong: true }
                            Lbl { text: modelData.bytesIn + " bytes in, " + modelData.bytesOut + " bytes out"; tone: "secondary"; size: Theme.caption }
                        }
                    }
                    PButton { visible: page.cloud.running; text: "Refresh"; enabled: !app.busy; onClicked: app.refresh() }
                }
            }
        }
    }

    FileDialog {
        id: fileDialog
        title: T.docsImport
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Documents (*.txt *.md *.pdf)"]
        onAccepted: app.importDocuments(page.activeGroup, selectedFiles.map(function (u) { return u.toString() }))
    }
}
