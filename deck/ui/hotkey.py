"""Hidden native message host for the global dashboard hotkey."""
from launchdeck_tray import TrayIcon

from deck.ui import state


class HotkeyHost(TrayIcon):
    """Keep RegisterHotKey on its owner thread without a taskbar icon."""

    def __init__(self):
        super().__init__(tip="LaunchDeck hotkey host", show_icon=False)

    def on_hotkey(self, hid):
        state.actions.put("toggle_ui")
