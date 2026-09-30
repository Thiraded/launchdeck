import ctypes
import queue
import unittest
from pathlib import Path
from unittest import mock

import launchdeck_core as core
from deck.core import jobs as _jobs
# Never open/kill a real deck job from a test (isolated namespace).
_jobs.PREFIX = "Local\\launchdeck-test-%d-" % __import__("os").getpid()
import launchdeck_tray


class Tests(unittest.TestCase):
    def test_pointer_safe_prototypes(self):
        tray = launchdeck_tray.TrayIcon()
        self.assertTrue(tray._init_ok, tray.last_error)
        self.assertIs(launchdeck_tray.kernel32.GetModuleHandleW.restype, ctypes.c_void_p)
        self.assertIs(launchdeck_tray.kernel32.GetConsoleWindow.restype, ctypes.c_void_p)

    def test_stop_posts_shutdown_without_cross_thread_destroy(self):
        tray, thread = launchdeck_tray.TrayIcon(), mock.Mock()
        tray.hwnd, tray._thread = 123, thread
        thread.is_alive.side_effect = [True, False]
        with mock.patch.object(launchdeck_tray.user32, 'PostMessageW', return_value=1) as post, mock.patch.object(launchdeck_tray.user32, 'DestroyWindow') as destroy:
            stopped = tray.stop(0.01)
        post.assert_called_once_with(123, launchdeck_tray.WM_APP_SHUTDOWN, 0, 0)
        thread.join.assert_called_once_with(0.01)
        destroy.assert_not_called()

    def test_main_icon_add_failure_is_reported(self):
        tray = launchdeck_tray.TrayIcon()
        tray.hwnd, tray.icon = 1, 2
        with mock.patch.object(launchdeck_tray.shell32, 'Shell_NotifyIconW', return_value=0):
            self.assertFalse(tray._add_icon())

    def test_secondary_icon_setversion_failure_uses_legacy_callbacks(self):
        tray = launchdeck_tray.TrayIcon()
        tray.hwnd = 1
        notify = mock.Mock(side_effect=[1, 0])
        with mock.patch.object(launchdeck_tray, 'make_square_icon', return_value=55), mock.patch.object(launchdeck_tray.shell32, 'Shell_NotifyIconW', notify), mock.patch.object(launchdeck_tray.user32, 'DestroyIcon') as destroy:
            self.assertEqual(tray.add_work_icon(100, 'Demo'), 55)
        self.assertEqual([call.args[0] for call in notify.call_args_list],
                         [launchdeck_tray.NIM_ADD, launchdeck_tray.NIM_SETVERSION])
        destroy.assert_not_called()

    def test_legacy_callback_routes_icon_id_from_wparam(self):
        tray = launchdeck_tray.TrayIcon()
        tray.on_tray_event = mock.Mock()
        old = launchdeck_tray._INSTANCE
        try:
            launchdeck_tray._INSTANCE = tray
            launchdeck_tray._wndproc(1, tray.msg, 100, launchdeck_tray.WM_LBUTTONUP)
        finally:
            launchdeck_tray._INSTANCE = old
        tray.on_tray_event.assert_called_once_with(
            100, launchdeck_tray.WM_LBUTTONUP)


    def test_dispatcher_executes_one_handler(self):
        from deck.ui import app, state
        dash = object.__new__(app.Dashboard)
        dash.toggle = mock.Mock()
        dash._handle_action('toggle_ui')
        dash.toggle.assert_called_once_with()


    def test_poll_isolates_action_failure_and_reschedules(self):
        from deck.ui import app, state
        dash = object.__new__(app.Dashboard)
        dash.root = mock.Mock()
        dash.visible = False
        dash._handle_action = mock.Mock(side_effect=[RuntimeError('boom'), None])
        test_actions = queue.Queue()
        test_actions.put('bad')
        test_actions.put('good')
        with mock.patch.object(state, 'actions', test_actions), mock.patch.object(state, 'log') as log:
            dash._poll()
        self.assertEqual(dash._handle_action.call_args_list,
                         [mock.call('bad'), mock.call('good')])
        log.assert_called_once()
        dash.root.after.assert_called_once_with(250, dash._poll)
    def test_one_action_consumer(self):
        source = ''.join(p.read_text(encoding='utf-8')
                         for p in Path('deck/ui').glob('*.py'))
        self.assertEqual(source.count('actions.get_nowait()'), 1)
        self.assertNotIn('def check_actions', source)


if __name__ == '__main__':
    unittest.main()
