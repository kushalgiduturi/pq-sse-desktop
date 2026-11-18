// Workspace: the working tools, by role. A rail on the left picks the role; each role
// shows only its own task sections, with one filled button in the section that is next.
// Quiet glass: everything is flat inside the page panel; a hairline divides rail and content.
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
    property int editId: -1                 // the document being edited, or -1 for a new one
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
    function cap(s) { void app.teachingNames; return app.displayName(s) }   // reading teachingNames re-runs bindings when it changes
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
        width: 220 * Math.min(1.5, Math.max(1, Theme.scale))
        height: parent.height
        Rectangle { parent: rail; anchors.right: parent.right; width: 1; height: parent.height; color: Theme.hair }
        Flickable {
          anchors.fill: parent
          contentHeight: railColumn.implicitHeight
          clip: true
          Column {
            id: railColumn
            width: parent.width - Theme.sp6
            spacing: Theme.sp1
            Txt { text: T.workAs; strong: true; bottomPadding: Theme.sp2 }
            Repeater {
                model: ["alice"].concat(page.doctors.map(function (d) { return d.name }),
                                        page.isAlice || page.isCloud || page.doctors.some(function (d) { return d.name === page.role }) ? [] : [page.role], ["cloud"])
                Rectangle {
                    id: roleItem
                    required property string modelData
                    readonly property bool on: page.role === modelData
                    width: railColumn.width
                    height: Math.max(56, roleText.implicitHeight + 16)
                    radius: Theme.rCard
                    color: on ? Theme.press : hov.hovered ? Theme.rowHover : "transparent"
                    border.width: activeFocus ? 2 : 0
                    border.color: Theme.ring
                    activeFocusOnTab: true
                    Accessible.role: Accessible.RadioButton
                    Accessible.name: page.cap(modelData)
                    Accessible.checked: on
                    Keys.onReturnPressed: app.setRole(modelData)
                    Keys.onSpacePressed: app.setRole(modelData)
                    Avatar { who: roleItem.modelData; size: 36; x: 10; anchors.verticalCenter: parent.verticalCenter }
                    Column {
                        id: roleText
                        x: 58; width: parent.width - 66; anchors.verticalCenter: parent.verticalCenter
                        Txt { text: page.cap(roleItem.modelData); strong: true; lineHeight: 1.3 }
                        Txt { text: roleItem.modelData === "alice" ? T.roleOwner : roleItem.modelData === "cloud" ? T.roleCloud : T.roleDoctor; tone: "secondary"; kind: "sm"; lineHeight: 1.3 }
                    }
                    HoverHandler { id: hov; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: app.setRole(roleItem.modelData) }
                }
            }
            Item { width: 1; height: Theme.sp4 }
            Field { id: newPerson; width: parent.width; label: T.addPerson; hint: T.addPersonHint; onAccepted: addButton.clicked() }
            Item { width: 1; height: Theme.sp1 }
            PButton { id: addButton; width: parent.width; text: T.addPerson; enabled: newPerson.text.trim().length > 0
                      onClicked: { app.setRole(newPerson.text.trim().toLowerCase()); newPerson.clear() } }
          }
        }
    }

    // ---------------------------------------------------------------- cards
    Flickable {
        id: scroller
        anchors.left: rail.right; anchors.leftMargin: Theme.sp8
        anchors.right: parent.right
        height: parent.height
        contentHeight: content.implicitHeight + 24
        clip: true
        readonly property real cardWidth: width > 760 ? (width - Theme.sp10) / 2 : width

        Column {
            id: content
            width: parent.width
            spacing: Theme.sp8
            Column {
                width: parent.width
                spacing: Theme.sp1
                Txt { text: page.fill(T.workspaceTitle, { role: page.cap(page.role) }); kind: "xl"; width: parent.width }
                Txt { text: T.workspaceSub + (app.practice ? " " + T.practicePass : ""); tone: "secondary"; width: Math.min(parent.width, 720) }
            }

            // "Let me try": the task from Journey stays visible while it is done by hand.
            Glass {
                visible: app.task.text !== undefined && app.task.text !== ""
                width: parent.width
                height: taskColumn.implicitHeight + 2 * padding
                depth: 1
                radius: Theme.rCard
                padding: Theme.sp5
                Column {
                    id: taskColumn
                    width: parent.width
                    spacing: 8
                    Txt { text: T.journeyTask + ": " + (app.task.title || ""); kind: "lg"; width: parent.width }
                    Txt { text: app.task.text || ""; tone: "secondary"; width: parent.width }
                    Row { visible: app.lessonCheck.step === app.task.step && app.lessonCheck.ok === false; spacing: Theme.sp2; width: parent.width
                          Icon { name: "alert"; size: 16; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter }
                          Txt { text: app.lessonCheck.text || ""; width: parent.width - 24 } }
                    Row { spacing: 10
                          PButton { primary: true; enabled: !app.busy; text: T.journeyCheck
                                    onClicked: { var step = app.task.step; app.checkLessonStep(step); if (app.lessonCheck.ok) app.navigate("journey") } }
                          PButton { text: T.journeyTaskClose; onClicked: app.clearTask() } }
                }
            }

            // ============================================================ Alice
            Flow {
                visible: page.isAlice
                width: parent.width
                spacing: Theme.sp10

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
                          text: T.startCloudFirst }
                }

                TaskCard {
                    width: scroller.cardWidth
                    title: T.cardDocuments
                    next: page.aliceNext === "documents"
                    hasMore: page.owner.groups.length > 0
                    summary: page.owner.groups.length === 0 ? T.docsNoGroup
                           : page.groupState.docs.length === 0 ? T.docsNone : page.fill(T.docsCount, { n: page.groupState.docs.length, g: page.activeGroup })
                    Flow { width: parent.width; spacing: Theme.sp2
                           Repeater { model: page.owner.groups
                                      Pick { required property var modelData; text: modelData.name; selected: page.activeGroup === modelData.name; onClicked: page.group = modelData.name } } }
                    Column {
                        width: parent.width
                        Repeater {
                        model: page.groupState.docs
                        Item {
                            id: docRow
                            required property var modelData
                            width: parent.width; height: Math.max(Theme.touch ? 48 : 44, docTitle.implicitHeight + 16)
                            Rectangle { anchors.fill: parent; anchors.leftMargin: -Theme.sp2; anchors.rightMargin: -Theme.sp2; radius: Theme.rSm
                                        color: docHover.hovered ? Theme.rowHover : "transparent" }
                            HoverHandler { id: docHover }
                            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
                            Icon { name: "document"; size: 18; color: Theme.text2; anchors.verticalCenter: parent.verticalCenter }
                            Txt { id: docTitle; x: 28; width: parent.width - docButtons.width - 36; anchors.verticalCenter: parent.verticalCenter; text: docRow.modelData.title; maximumLineCount: 1; elide: Text.ElideRight; wrapMode: Text.NoWrap; lineHeight: 1.2 }
                            Row {
                                id: docButtons
                                anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter
                                PButton { quiet: true; text: T.docsEdit
                                          Accessible.name: T.docsEdit + " " + docRow.modelData.title
                                          onClicked: { page.editId = docRow.modelData.id; docTitleField.text = docRow.modelData.title; docText.text = docRow.modelData.text } }
                                PButton { quiet: true; text: T.docsDelete
                                          enabled: !app.busy; Accessible.name: T.docsDelete + " " + docRow.modelData.title
                                          onClicked: app.deleteDocument(page.activeGroup, docRow.modelData.id) }
                            }
                        }
                        }
                    }
                    Item { width: 1; height: Theme.sp2; visible: page.owner.groups.length > 0 }
                    Field { id: docTitleField; visible: page.owner.groups.length > 0; width: parent.width; hint: T.docsTitleHint }
                    Item {
                        visible: page.owner.groups.length > 0
                        width: parent.width; height: 104
                        Surface { anchors.fill: parent; depth: 1; radius: Theme.rCtl; padding: 0 }
                        Rectangle { visible: docText.activeFocus; anchors.fill: parent; anchors.margins: -2; radius: Theme.rCtl + 2
                                    color: "transparent"; border.width: 2; border.color: Theme.ring }
                        Txt { visible: docText.text.length === 0; x: 16; y: 11; text: T.docsTextHint; tone: "tertiary" }
                        Flickable {
                            anchors.fill: parent; anchors.leftMargin: 16; anchors.rightMargin: 16; anchors.topMargin: 11; anchors.bottomMargin: 10; clip: true; contentHeight: docText.implicitHeight
                            TextEdit { id: docText; width: parent.width; wrapMode: TextEdit.Wrap; color: Theme.text; selectionColor: Theme.accent; selectedTextColor: Theme.accentInk
                                       font.family: Theme.ui; font.pixelSize: Theme.fsMd; activeFocusOnTab: true; selectByMouse: true
                                       Accessible.role: Accessible.EditableText; Accessible.name: T.docsTextHint; KeyNavigation.priority: KeyNavigation.BeforeItem; KeyNavigation.tab: docAdd }
                        }
                    }
                    PButton { id: docAdd; visible: page.owner.groups.length > 0; primary: page.aliceNext === "documents"; enabled: !app.busy && docText.text.trim().length > 0
                              text: page.editId >= 0 ? T.docsSave : T.docsAddBtn
                              onClicked: { if (page.editId >= 0) app.editDocument(page.activeGroup, page.editId, docTitleField.text, docText.text)
                                           else app.addDocument(page.activeGroup, docTitleField.text, docText.text)
                                           page.editId = -1; docTitleField.clear(); docText.text = "" } }
                    PButton { visible: page.editId >= 0; quiet: true; text: T.docsCancelEdit; onClicked: { page.editId = -1; docTitleField.clear(); docText.text = "" } }
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
                    Column {
                        width: parent.width
                        Repeater {
                            model: page.owner.people
                            Item {
                                id: personRow
                                required property var modelData
                                width: parent.width; height: 52
                                Avatar { who: personRow.modelData.name; size: 32; anchors.verticalCenter: parent.verticalCenter }
                                Column {
                                    x: 44; width: parent.width - 44 - personPill.width - 12; anchors.verticalCenter: parent.verticalCenter
                                    Txt { text: page.cap(personRow.modelData.name); strong: true; lineHeight: 1.3 }
                                    Txt { visible: !personRow.modelData.revoked; text: personRow.modelData.groups.join(", "); kind: "sm"; tone: "secondary"; lineHeight: 1.3; width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                                }
                                Pill { id: personPill; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                                       text: personRow.modelData.revoked ? T.peopleRevokedPill : T.peopleActive; status: personRow.modelData.revoked ? "bad" : "ok" }
                                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.hair }
                            }
                        }
                    }
                    Repeater {
                        model: page.owner.pending
                        Column {
                            id: pend
                            required property var modelData
                            width: parent.width; spacing: 6
                            Lbl { width: parent.width; text: page.fill(T.joinRequestLine, { who: page.cap(pend.modelData.name), fp: pend.modelData.fingerprint }); strong: true }
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
                                  text: page.fill(T.publishState, { g: pub.modelData.name, ver: pub.modelData.version, e: pub.modelData.epoch, n: pub.modelData.entries,
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
                    Segmented { visible: page.owner.people.length > 0; width: Math.min(parent.width, 360); name: T.policyName; labels: [T.revokeQuick, T.revokeThorough]
                                current: page.policy === "R" ? 0 : 1; onChosen: (i) => page.policy = i === 0 ? "R" : "RE" }
                    Txt { visible: page.owner.people.length > 0; width: parent.width; text: page.policy === "R" ? T.revokeQuickNote : T.revokeThoroughNote; tone: "secondary"; kind: "sm" }
                    PButton { visible: page.owner.people.length > 0; danger: true; primary: page.revokeUid !== ""; enabled: !app.busy && page.revokeUid !== ""; text: T.revokeBtn
                              onClicked: { app.revoke(page.revokeUid, page.policy); page.revokeUid = "" } }
                }
            }

            // ============================================================ a doctor
            Flow {
                visible: !page.isAlice && !page.isCloud
                width: parent.width
                spacing: Theme.sp10

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
                    caution: page.doctor.result.failed === true
                    summary: checks.length === 0 ? T.verifyNone : page.doctor.result.failed ? T.verifyFailed : page.fill(T.verifyAll, { n: checks.length })
                    Flow {
                        width: parent.width; spacing: Theme.sp2
                        Repeater {
                            model: verifyCard.checks
                            Chip { required property var modelData; maxWidth: verifyCard.width; text: modelData.name + (modelData.ok ? "" : ": " + modelData.detail); mark: modelData.ok ? "ok" : "fail" }
                        }
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
                    Txt { visible: page.doctor.opened.title !== undefined; width: parent.width; text: page.doctor.opened.title || ""; kind: "lg" }
                    Lbl { visible: page.doctor.opened.title !== undefined; width: parent.width; text: page.doctor.opened.text || ""; tone: "secondary" }
                }
            }

            // ============================================================ the cloud
            Flow {
                visible: page.isCloud
                width: parent.width
                spacing: Theme.sp10

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
                        Lbl { required property var modelData; width: parent.width; text: Theme.fmt(T.storesEntry, { address: modelData.address, value: modelData.value })
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
                            spacing: Theme.sp4
                            height: 32
                            Txt { width: 80; text: modelData.time; tone: "tertiary"; kind: "mono"; anchors.verticalCenter: parent.verticalCenter }
                            Txt { width: 160; text: modelData.endpoint; kind: "sm"; strong: true; anchors.verticalCenter: parent.verticalCenter }
                            Txt { text: Theme.fmt(T.logBytes, { in: modelData.bytesIn, out: modelData.bytesOut }); tone: "secondary"; kind: "mono"; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                    PButton { visible: page.cloud.running; text: T.refresh; enabled: !app.busy; onClicked: app.refresh() }
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
