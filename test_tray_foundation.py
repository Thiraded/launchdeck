import ctypes
import queue
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import wc_core as core
import wc_tray


class Fn:
    def __init__(self, fn=lambda *a: 1):
        self.fn, self.calls, self.argtypes, self.restype = fn, [], None, None

    def __call__(self, *args):
        self.calls.append(args)
        return self.fn(*args)


class FakeUser32:
    def __init__(self):
        self.visible = {10: False}
        self.IsWindow = Fn(lambda h: h == 10)
        self.IsWindowVisible = Fn(lambda h: self.visible.get(h, False))
        self.ShowWindowAsync = Fn(self.show)

    def show(self, hwnd, command):
        self.visible[hwnd] = command != 0
        return 0


class Tests(unittest.TestCase):
    def tearDown(self):
        with core._HIDDEN_LOCK:
            core._HIDDEN_HWNDS.clear()
            core._HIDDEN_HWND_PIDS.clear()

    def test_pointer_safe_prototypes(self):
        tray = wc_tray.TrayIcon()
        self.assertTrue(tray._init_ok, tray.last_error)
        self.assertIs(wc_tray.kernel32.GetModuleHandleW.restype, ctypes.c_void_p)
        self.assertIs(wc_tray.kernel32.GetConsoleWindow.restype, ctypes.c_void_p)

    def test_stop_posts_shutdown_without_cross_thread_destroy(self):
        tray, thread = wc_tray.TrayIcon(), mock.Mock()
        tray.hwnd, tray._thread = 123, thread
        thread.is_alive.side_effect = [True, False]
        with mock.patch.object(wc_tray.user32, 'PostMessageW', return_value=1) as post, mock.patch.object(wc_tray.user32, 'DestroyWindow') as destroy:
            stopped = tray.stop(0.01)
        post.assert_called_once_with(123, wc_tray.WM_APP_SHUTDOWN, 0, 0)
        thread.join.assert_called_once_with(0.01)
        destroy.assert_not_called()

    def test_restore_confirms_visibility_and_uses_sw_restore(self):
        api = FakeUser32()
        with mock.patch.object(ctypes, 'windll', SimpleNamespace(user32=api)):
            self.assertEqual(core.set_hwnds_visible([10], True), 1)
        self.assertEqual(api.ShowWindowAsync.calls, [(10, 9)])

    def test_invalid_hidden_handle_is_pruned(self):
        work = {'id': 'demo'}
        with core._HIDDEN_LOCK:
            core._HIDDEN_HWNDS['demo'] = [77]
        with mock.patch.object(core, '_valid_hwnds', return_value=[]):
            count, message = core.show_work_windows(work)
        self.assertEqual(count, 0)
        self.assertIn('no longer exists', message)
        self.assertFalse(core.is_work_hidden(work))

    def test_sweep_skips_restoring_work(self):
        work = {'id': 'demo'}
        with core._HIDDEN_LOCK:
            core._HIDDEN_HWNDS['demo'] = [1]
            core._RESTORING_WORKS.add('demo')
        with mock.patch.object(core, 'find_work_hwnds') as find:
            self.assertEqual(core.sweep_hidden_windows({'works': [work]}), {})
        find.assert_not_called()

    def test_reused_hwnd_owner_is_rejected(self):
        with mock.patch.object(core, '_hwnd_owner_pids', return_value={10: 999}), mock.patch.object(core, '_valid_hwnds', wraps=core._valid_hwnds):
            with mock.patch.object(ctypes, 'windll', SimpleNamespace(user32=FakeUser32())):
                self.assertEqual(core._valid_hwnds([10], {10: 111}), [])

    def test_main_icon_add_failure_is_reported(self):
        tray = wc_tray.TrayIcon()
        tray.hwnd, tray.icon = 1, 2
        with mock.patch.object(wc_tray.shell32, 'Shell_NotifyIconW', return_value=0):
            self.assertFalse(tray._add_icon())

    def test_secondary_icon_setversion_failure_uses_legacy_callbacks(self):
        tray = wc_tray.TrayIcon()
        tray.hwnd = 1
        notify = mock.Mock(side_effect=[1, 0])
        with mock.patch.object(wc_tray, 'make_square_icon', return_value=55), mock.patch.object(wc_tray.shell32, 'Shell_NotifyIconW', notify), mock.patch.object(wc_tray.user32, 'DestroyIcon') as destroy:
            self.assertEqual(tray.add_work_icon(100, 'Demo'), 55)
        self.assertEqual([call.args[0] for call in notify.call_args_list],
                         [wc_tray.NIM_ADD, wc_tray.NIM_SETVERSION])
        destroy.assert_not_called()

    def test_legacy_callback_routes_icon_id_from_wparam(self):
        tray = wc_tray.TrayIcon()
        tray.on_tray_event = mock.Mock()
        old = wc_tray._INSTANCE
        try:
            wc_tray._INSTANCE = tray
            wc_tray._wndproc(1, tray.msg, 100, wc_tray.WM_LBUTTONUP)
        finally:
            wc_tray._INSTANCE = old
        tray.on_tray_event.assert_called_once_with(
            100, wc_tray.WM_LBUTTONUP)


    def test_partial_restore_keeps_parked_icon(self):
        import wctray
        tray = wctray.WorkTray()
        tray.parked['demo'] = {'uid': 100, 'hicon': 55, 'label': 'Demo'}
        with mock.patch.object(wctray, 'work_by_id', return_value={'id': 'demo'}), mock.patch.object(core, 'show_work_windows', return_value=(0, 'incomplete')), mock.patch.object(core, 'is_work_hidden', return_value=True), mock.patch.object(tray, 'del_work_icon') as delete:
            self.assertEqual(tray.unpark_work('demo', restore=True), 'incomplete')
        self.assertIn('demo', tray.parked)
        delete.assert_not_called()

    def test_dispatcher_executes_one_handler(self):
        import wctray
        dash = object.__new__(wctray.Dashboard)
        dash.toggle = mock.Mock()
        dash._handle_action('toggle_ui')
        dash.toggle.assert_called_once_with()


    def test_poll_isolates_action_failure_and_reschedules(self):
        import wctray
        dash = object.__new__(wctray.Dashboard)
        dash.root = mock.Mock()
        dash.visible = False
        dash._handle_action = mock.Mock(side_effect=[RuntimeError('boom'), None])
        test_actions = queue.Queue()
        test_actions.put('bad')
        test_actions.put('good')
        with mock.patch.object(wctray, 'actions', test_actions), mock.patch.object(wctray, 'log') as log:
            dash._poll()
        self.assertEqual(dash._handle_action.call_args_list,
                         [mock.call('bad'), mock.call('good')])
        log.assert_called_once()
        dash.root.after.assert_called_once_with(250, dash._poll)
    def test_one_action_consumer(self):
        source = Path('wctray.py').read_text(encoding='utf-8')
        self.assertEqual(source.count('actions.get_nowait()'), 1)
        self.assertNotIn('def check_actions', source)


if __name__ == '__main__':
    unittest.main()
