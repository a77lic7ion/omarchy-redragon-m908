import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "redragon-m908"

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function togglePanel() { if (panelLoader.item) panelLoader.item.toggle() }
  // The bar's popout coordinator prefers this over close() when swapping
  // panels; KeyboardPanel reads the flag back off its owner.
  readonly property bool popoutSwitchClosing: panelLoader.item
    ? panelLoader.item.popoutSwitchClosing === true : false
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  // The clock plugin's contract: the panel is a Loader child, and these are
  // handed to it once it exists. Panel.qml declares `anchorItem` itself.
  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    hasVisualContent: true
    labelVisible: false
    implicitWidth: root.vertical ? barSize : Math.max(Style.space(26), letter.implicitWidth + Style.space(16))
    implicitHeight: root.vertical ? barSize : Style.space(26)
    tooltipText: "Redragon M908"

    onPressed: function (b) {
      if (b === Qt.LeftButton) root.togglePanel()
    }

    Text {
      id: letter
      anchors.centerIn: parent
      text: "R"
      font.family: "JetBrains Mono"
      font.pixelSize: Style.font.body
      font.bold: true
      color: (root.opened || button.tooltipHovered) ? Color.accent : Color.urgent
    }
  }
}
