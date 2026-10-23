import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "redragon-m908"
  ipcTarget: "redragon-m908"
  manageIpc: true

  // Handed to us by BarWidget.qml's injectPanel() once the bar button exists.
  property var anchorItem: null

  property var buttons: ({})
  property var profileList: []
  property string activeName: "default"
  property string errorText: ""
  property bool daemonUp: false
  property string capturing: ""      // button id awaiting a key press
  property string selected: "side_1" // button shown in the editor
  property bool detecting: false     // waiting for a press on the mouse itself
  property int detectPolls: 0

  // Mirrors daemon/buttonmap.py BUTTON_ORDER.
  readonly property var order: [
    "side_1", "side_2", "side_3", "side_4", "side_5", "side_6",
    "side_7", "side_8", "side_9", "side_10", "side_11", "side_12", "top"
  ]

  // Geometry of the numbered hotspots on the mouse diagram.
  readonly property var sideHotspots: [
    { id: "side_1", n: 1, col: 0, row: 0 },
    { id: "side_2", n: 2, col: 1, row: 0 },
    { id: "side_3", n: 3, col: 0, row: 1 },
    { id: "side_4", n: 4, col: 1, row: 1 },
    { id: "side_5", n: 5, col: 0, row: 2 },
    { id: "side_6", n: 6, col: 1, row: 2 },
    { id: "side_7", n: 7, col: 0, row: 3 },
    { id: "side_8", n: 8, col: 1, row: 3 },
    { id: "side_9", n: 9, col: 0, row: 4 },
    { id: "side_10", n: 10, col: 1, row: 4 },
    { id: "side_11", n: 11, col: 0, row: 5 },
    { id: "side_12", n: 12, col: 1, row: 5 }
  ]

  function labelFor(id) {
    if (!buttons[id]) return id
    return buttons[id].label ? buttons[id].label : id
  }
  function displayFor(id) {
    if (!buttons[id]) return "Disabled"
    return buttons[id].display ? buttons[id].display : "Disabled"
  }
  function isDisabled(id) {
    return !buttons[id] || buttons[id].type === "disabled"
  }

  // ---- daemon socket -------------------------------------------------------
  // Quickshell's Socket reads through `parser`, not onRead/readData, and a
  // failed connect leaves a dead socket behind - setting connected=true again
  // is a no-op, so each retry recreates the Socket via the Loader below.
  property int reconnectAttempt: 0

  Component {
    id: socketComponent
    Socket {
      path: Quickshell.env("XDG_RUNTIME_DIR") + "/m908.sock"
      connected: true
      parser: SplitParser {
        splitMarker: "\n"
        onRead: function (line) { root.handleLine(line) }
      }
      onConnectionStateChanged: {
        if (connected) {
          root.reconnectAttempt = 0
          root.errorText = ""
          root.daemonUp = true
          // The Loader has not assigned `item` yet while this signal fires,
          // so defer until the Socket is reachable through socketLoader.item.
          Qt.callLater(root.refresh)
        } else {
          root.daemonUp = false
          if (root.errorText === "") root.errorText = "Daemon offline"
        }
      }
    }
  }

  Loader {
    id: socketLoader
    active: false
    sourceComponent: socketComponent
  }

  // Keeps the daemon's per-connection idle timeout from closing us.
  Timer {
    interval: 30000
    repeat: true
    running: root.daemonUp
    onTriggered: root.refresh()
  }

  Timer {
    id: reconnectTimer
    interval: Math.min(1500, 180 + root.reconnectAttempt * 120)
    repeat: true
    triggeredOnStart: true
    running: !root.daemonUp
    onTriggered: {
      root.reconnectAttempt = Math.min(12, root.reconnectAttempt + 1)
      socketLoader.active = false
      socketLoader.active = true
    }
  }

  function handleLine(line) {
    line = String(line)
    if (line.trim() === "") return
    var resp
    try { resp = JSON.parse(line) } catch (e) { return }
    root.applyResponse(resp)
  }

  function send(op, extra) {
    var sock = socketLoader.item
    if (!sock || !sock.connected) {
      root.errorText = "Daemon offline"
      return
    }
    sock.write(JSON.stringify(Object.assign({ "op": op }, extra || {})) + "\n")
    sock.flush()
  }

  function refresh() {
    send("status")
    send("profiles.list")
  }

  function applyResponse(resp) {
    if (!resp) return
    if (resp.ok === false) {
      if (resp.error) root.errorText = resp.error
      return
    }
    if (root.detecting && resp.code !== undefined) {
      root.detecting = false
      detectTimer.stop()
      if (resp.button) {
        root.selected = resp.button
        root.errorText = ""
      } else if (resp.code !== null) {
        root.errorText = "That press was not a side button — try again"
      }
      return
    }
    if (resp.connected !== undefined) root.daemonUp = resp.connected
    if (resp.buttons) root.buttons = resp.buttons
    if (resp.active !== undefined) root.activeName = resp.active
    if (resp.profiles) {
      root.profileList = resp.profiles.map(function (p) {
        return typeof p === "string" ? { slug: p, name: p } : p
      })
    }
  }

  // ---- actions -------------------------------------------------------------
  function loadProfile(slug) {
    send("profile.load", { "slug": slug })
    refresh()
  }
  function createProfile() {
    var name = newNameField.text.trim()
    if (name === "") { root.errorText = "Type a name for the new profile"; return }
    send("profile.new", { "name": name, "base": root.activeName })
    newNameField.text = ""
    refresh()
  }
  function deleteActive() {
    if (root.activeName === "default") {
      root.errorText = "The default profile cannot be deleted"
      return
    }
    send("profile.delete", { "slug": root.activeName })
    refresh()
  }
  function setAction(type, value) {
    if (root.selected === "") return
    send("button.set", { "button": root.selected, "type": type, "value": value })
    refresh()
  }
  function resetSelected() {
    send("button.reset", { "button": root.selected })
    refresh()
  }
  function startCapture() {
    root.errorText = ""
    root.capturing = root.selected
    Qt.callLater(function () { captureLayer.forceActiveFocus() })
  }
  function cancelCapture() {
    root.capturing = ""
    root.errorText = ""
  }
  function assignCaptured(code) {
    root.capturing = ""
    if (code > 0) setAction("key", code)
  }

  // Closing the panel must not leave the daemon swallowing the next press.
  onOpenedChanged: {
    if (root.opened) return
    if (root.capturing !== "") root.cancelCapture()
    if (root.detecting) root.stopDetect(true)
  }

  function startDetect() {
    root.errorText = ""
    root.detectPolls = 0
    root.detecting = true
    send("button.capture")
    detectTimer.start()
  }
  function stopDetect(silent) {
    if (!root.detecting) return
    root.detecting = false
    detectTimer.stop()
    send("button.capture.cancel")
    if (!silent) root.errorText = "No button detected — try again"
  }

  Timer {
    id: detectTimer
    interval: 250
    repeat: true
    onTriggered: {
      if (root.detectPolls++ > 40) { root.stopDetect(false); return }
      send("button.capture.poll")
    }
  }

  Process {
    id: restartDaemon
    command: ["systemctl", "--user", "restart", "m908d"]
    onExited: function (code) {
      if (code === 0) root.errorText = ""
      else root.errorText = "Could not restart m908d"
      Qt.callLater(root.refresh)
    }
  }

  // Qt key -> Linux evdev code. Verified against input-event-codes.h; the
  // previous table here was shifted by one row and produced wrong bindings.
  function evdevForKey(key) {
    if (key >= Qt.Key_A && key <= Qt.Key_Z)
      return [30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38, 50,
              49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44][key - Qt.Key_A]
    if (key >= Qt.Key_0 && key <= Qt.Key_9)
      return key === Qt.Key_0 ? 11 : key - Qt.Key_0 + 1
    if (key >= Qt.Key_F1 && key <= Qt.Key_F12)
      return [59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 87, 88][key - Qt.Key_F1]

    switch (key) {
    case Qt.Key_Escape: return 1
    case Qt.Key_Tab: return 15
    case Qt.Key_Backtab: return 15
    case Qt.Key_Backspace: return 14
    case Qt.Key_Return: return 28
    case Qt.Key_Enter: return 28
    case Qt.Key_Space: return 57
    case Qt.Key_Insert: return 110
    case Qt.Key_Delete: return 111
    case Qt.Key_Home: return 102
    case Qt.Key_End: return 107
    case Qt.Key_PageUp: return 104
    case Qt.Key_PageDown: return 109
    case Qt.Key_Left: return 105
    case Qt.Key_Right: return 106
    case Qt.Key_Up: return 103
    case Qt.Key_Down: return 108
    case Qt.Key_Minus: return 12
    case Qt.Key_Equal: return 13
    case Qt.Key_BracketLeft: return 26
    case Qt.Key_BracketRight: return 27
    case Qt.Key_Semicolon: return 39
    case Qt.Key_Apostrophe: return 40
    case Qt.Key_QuoteLeft: return 41
    case Qt.Key_Backslash: return 43
    case Qt.Key_Comma: return 51
    case Qt.Key_Period: return 52
    case Qt.Key_Slash: return 53
    case Qt.Key_Shift: return 42
    case Qt.Key_Control: return 29
    case Qt.Key_Alt: return 56
    case Qt.Key_Meta: return 125
    case Qt.Key_CapsLock: return 58
    case Qt.Key_NumLock: return 69
    case Qt.Key_ScrollLock: return 70
    case Qt.Key_Pause: return 119
    case Qt.Key_Print: return 99
    }
    return 0
  }

  // ---- panel ---------------------------------------------------------------
  KeyboardPanel {
    id: popup
    anchorItem: root.anchorItem
    owner: root
    bar: root.bar
    open: root.opened
    padding: Style.space(10)
    contentWidth: popup.fittedContentWidth(Style.space(560))
    contentHeight: popup.fittedContentHeight(content.implicitHeight)

    ColumnLayout {
      id: content
      width: parent.width
      spacing: Style.space(7)

      // ---- header -----------------------------------------------------
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(6)

        Text {
          text: "Redragon M908"
          color: root.barForeground
          font.family: Style.font.family
          font.pixelSize: Style.font.title
          Layout.alignment: Qt.AlignVCenter
        }

        Rectangle {
          radius: height / 2
          color: root.daemonUp ? Color.accent : Color.background
          border.width: 1
          border.color: root.daemonUp ? Color.accent : Color.urgent
          implicitWidth: stateText.implicitWidth + Style.space(12)
          implicitHeight: stateText.implicitHeight + Style.space(3)

          Text {
            id: stateText
            anchors.centerIn: parent
            text: root.daemonUp ? "active" : "daemon offline"
            color: root.daemonUp ? Color.background : Color.urgent
            font.pixelSize: Style.font.caption
          }
        }

        Item { Layout.fillWidth: true }

        PanelActionButton {
          iconText: "↻"
          tooltipText: "Restart the m908d daemon"
          onClicked: restartDaemon.running = true
        }
      }

      Text {
        Layout.fillWidth: true
        visible: !root.daemonUp
        text: "Start it with:  systemctl --user start m908d"
        color: Color.urgent
        font.family: "JetBrains Mono"
        font.pixelSize: Style.font.caption
      }

      // ---- profiles ---------------------------------------------------
      PanelSectionHeader { text: "Profile" }

      Flow {
        Layout.fillWidth: true
        spacing: Style.space(5)

        Repeater {
          model: root.profileList
          delegate: Rectangle {
            id: chip
            required property var modelData
            readonly property bool isActive: modelData.slug === root.activeName

            implicitWidth: Math.max(Style.space(64), chipText.implicitWidth + Style.space(14))
            implicitHeight: Style.space(24)
            radius: height / 2
            color: isActive ? Color.accent : "transparent"
            border.width: 1
            border.color: isActive ? Color.accent : Color.foreground

            Text {
              id: chipText
              anchors.centerIn: parent
              text: chip.modelData.name
              color: chip.isActive ? Color.background : root.barForeground
              font.family: Style.font.family
              font.pixelSize: Style.font.body
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.loadProfile(chip.modelData.slug)
            }
          }
        }
      }

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(5)

        TextField {
          id: newNameField
          Layout.fillWidth: true
          implicitHeight: Style.space(26)
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          placeholderText: "New profile name"
          onAccepted: root.createProfile()
        }

        Button { text: "Create"; onClicked: root.createProfile() }
        Button {
          text: "Delete"
          foreground: Color.urgent
          onClicked: root.deleteActive()
        }
      }

      PanelSeparator {}

      // ---- mouse diagram + editor ------------------------------------
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(10)

        Item {
          id: diagram
          Layout.preferredWidth: Style.space(210)
          Layout.preferredHeight: Style.space(318)

          // Body
          Rectangle {
            x: Style.space(112); y: Style.space(18)
            width: Style.space(86); height: Style.space(284)
            radius: width / 2
            color: Color.background
            border.width: 1
            border.color: Color.foreground
            opacity: 0.9
          }

          // Split between the two main buttons
          Rectangle {
            x: Style.space(155); y: Style.space(20)
            width: 1; height: Style.space(76)
            color: Color.foreground
            opacity: 0.5
          }

          // Scroll wheel
          Rectangle {
            x: Style.space(149); y: Style.space(48)
            width: Style.space(13); height: Style.space(42)
            radius: width / 2
            color: Color.accent
            opacity: 0.35
          }

          // Side button hotspots
          Repeater {
            model: root.sideHotspots
            delegate: Rectangle {
              id: dot
              required property var modelData
              readonly property bool isSelected: root.selected === modelData.id
              readonly property bool isMapped: !root.isDisabled(modelData.id)

              x: Style.space(18) + modelData.col * Style.space(42)
              y: Style.space(44) + modelData.row * Style.space(42)
              width: Style.space(32); height: Style.space(32)
              radius: width / 2
              color: isSelected ? Color.accent
                     : (isMapped ? Qt.alpha(Color.accent, 0.14) : "transparent")
              border.width: 1
              border.color: isSelected ? Color.accent
                          : (isMapped ? Color.accent : Color.foreground)
              opacity: isMapped || isSelected ? 1.0 : 0.55

              Text {
                anchors.centerIn: parent
                text: dot.modelData.n
                color: dot.isSelected ? Color.background
                     : (dot.isMapped ? Color.accent : Color.foreground)
                font.family: "JetBrains Mono"
                font.pixelSize: Style.font.body
                font.bold: true
              }

              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.selected = dot.modelData.id
              }
            }
          }

          // Top button hotspot
          Rectangle {
            id: topHotspot
            readonly property bool isSelected: root.selected === "top"
            readonly property bool isMapped: !root.isDisabled("top")
            x: Style.space(140); y: Style.space(112)
            width: Style.space(30); height: Style.space(30)
            radius: width / 2
            color: isSelected ? Color.accent
                   : (isMapped ? Qt.alpha(Color.accent, 0.14) : "transparent")
            border.width: 1
            border.color: isSelected ? Color.accent
                        : (isMapped ? Color.accent : Color.foreground)

            Text {
              anchors.centerIn: parent
              text: "T"
              color: topHotspot.isSelected ? Color.background
                   : (topHotspot.isMapped ? Color.accent : Color.foreground)
              font.family: "JetBrains Mono"
              font.pixelSize: Style.font.caption
              font.bold: true
            }

            MouseArea {
              anchors.fill: parent
              cursorShape: Qt.PointingHandCursor
              onClicked: root.selected = "top"
            }
          }

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            text: "click a numbered button"
            color: Color.foreground
            opacity: 0.5
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
        }

        ColumnLayout {
          Layout.fillWidth: true
          Layout.alignment: Qt.AlignTop
          spacing: Style.space(6)

          Text {
            text: root.labelFor(root.selected)
            color: root.barForeground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            font.bold: true
          }

          Rectangle {
            Layout.fillWidth: true
            implicitHeight: Style.space(38)
            radius: Style.cornerRadius
            color: Color.background
            border.width: 1
            border.color: Color.foreground

            Text {
              anchors.centerIn: parent
              text: root.displayFor(root.selected)
              color: root.isDisabled(root.selected) ? Color.foreground : Color.accent
              opacity: root.isDisabled(root.selected) ? 0.6 : 1.0
              font.family: "JetBrains Mono"
              font.pixelSize: Style.font.subtitle
            }
          }

          Button {
            Layout.fillWidth: true
            text: root.detecting ? "Press a mouse button…" : "🖱  Find on mouse"
            selected: root.detecting
            onClicked: root.detecting ? root.stopDetect(false) : root.startDetect()
          }
          Button {
            Layout.fillWidth: true
            text: "⌨  Press a key…"
            onClicked: root.startCapture()
          }

          PanelSeparator {}

          RowLayout {
            Layout.fillWidth: true
            spacing: Style.space(5)

            Button {
              Layout.fillWidth: true
              text: "Disable"
              onClicked: root.setAction("disabled", null)
            }
            Button {
              Layout.fillWidth: true
              text: "↺ Factory"
              onClicked: root.resetSelected()
            }
          }

          Text {
            Layout.fillWidth: true
            text: "Applies system-wide while m908d is running — including full-screen games."
            color: Color.foreground
            opacity: 0.55
            wrapMode: Text.WordWrap
            font.family: Style.font.family
            font.pixelSize: Style.font.caption
          }
        }
      }

      // ---- message ----------------------------------------------------
      Rectangle {
        Layout.fillWidth: true
        visible: root.errorText !== ""
        implicitHeight: visible ? msg.implicitHeight + Style.space(10) : 0
        radius: Style.cornerRadius
        color: Color.background

        Text {
          id: msg
          anchors.centerIn: parent
          width: parent.width - Style.space(12)
          horizontalAlignment: Text.AlignHCenter
          wrapMode: Text.WordWrap
          font.family: Style.font.family
          font.pixelSize: Style.font.body
          color: Color.urgent
          text: root.errorText
        }
      }

      Text {
        Layout.fillWidth: true
        text: "The 4 DPI keys on top are handled by the mouse firmware and are not remappable here."
        color: Color.foreground
        opacity: 0.5
        wrapMode: Text.WordWrap
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
      }
    }

    // Key-capture layer. Sits above the content only while capturing so it
    // swallows the next key press instead of activating a control.
    Rectangle {
      id: captureLayer
      anchors.fill: parent
      visible: root.capturing !== ""
      color: Qt.alpha(Color.background, 0.92)
      focus: visible
      Keys.priority: Keys.BeforeItem
      Keys.onPressed: function (event) {
        if (root.capturing === "") return
        event.accepted = true
        if (event.key === Qt.Key_Escape) {
          root.cancelCapture()
          return
        }
        // Ignore modifier-only presses so Shift+key still maps the base key.
        if (event.key === Qt.Key_Shift || event.key === Qt.Key_Control
            || event.key === Qt.Key_Alt || event.key === Qt.Key_Meta)
          return
        var code = root.evdevForKey(event.key)
        if (code > 0) {
          root.assignCaptured(code)
        } else {
          root.capturing = ""
          root.errorText = "That key is not supported yet — try a letter, number or function key"
        }
      }

      Column {
        anchors.centerIn: parent
        spacing: Style.space(8)

        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: "Press a key for " + root.labelFor(root.capturing)
          color: root.barForeground
          font.family: Style.font.family
          font.pixelSize: Style.font.title
        }
        Text {
          anchors.horizontalCenter: parent.horizontalCenter
          text: "Esc to cancel"
          color: Color.foreground
          opacity: 0.6
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }
      }
    }
  }
}
